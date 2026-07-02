"""
fenix_backend.py  –  Escudería Fénix
- Escucha MQTT y guarda en InfluxDB
- Calcula variables derivadas del tren motriz
- Calcula orientación (Roll/Pitch) y aceleraciones compensadas (dinámica vehicular)
- Empuja cada snapshot a fenix_api via HTTP POST (RAM)
- Watchdog: si no llegan datos MQTT en 5s, envía snapshot con todo en cero
"""

import json
import math
import time
import threading
import requests
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# ─── Configuración MQTT ───────────────────────────────────────────────────────
MQTT_HOST  = "localhost"
MQTT_PORT  = 1883
MQTT_USER  = "fenix25"
MQTT_PASS  = "pswTeleFenix"
MQTT_TOPIC = "fenix/mgt/snapshot"

# ─── Configuración InfluxDB ───────────────────────────────────────────────────
INFLUX_URL    = "http://localhost:8086"
INFLUX_TOKEN  = "LIYzY_Q_DaHCXNDQ3fpkfnTxh9Lx_-wITjXy-3jlGyccx0LpB0yozjM-dpVf6_0YMHjZxS7m4ZTvG7wHVtzrjg=="
INFLUX_ORG    = "Escuderia Fenix UPIITA"
INFLUX_BUCKET = "Telemetria"

# ─── URL interna de fenix_api ─────────────────────────────────────────────────
API_INTERNAL_URL = "http://localhost:8050/internal/snapshot"

# ─── Constantes del motor y paquete ──────────────────────────────────────────
KT              = 0.143
E_NOM           = 5210.0
Q_NOM           = 100.0
I_MIN           = 10.0
T_REPOSO        = 60.0
T_GAP_MAX       = 600.0
SOC_MIN_DELTA   = 30.0
DT              = 0.1

# ─── Constantes conteo de vueltas ────────────────────────────────────────────
LAP_DEBOUNCE    = 10.0    # s mínimos entre dos cruces válidos
LAP_T_MIN       = 30.0    # s mínimos de duración de una vuelta
LAP_N_CAL       = 5       # vueltas usadas para calibrar la distancia de referencia
LAP_D_TOL       = 0.15    # tolerancia ±15% sobre la distancia de referencia
EARTH_R_KM      = 6371.0
META_HTTP_PORT  = 8060    # puerto del servidor HTTP interno para /set_meta

# ─── Watchdog ─────────────────────────────────────────────────────────────────
WATCHDOG_TIMEOUT = 5.0   # segundos sin datos MQTT → enviar ceros
_watchdog_timer  = None

# ─── Constantes batería auxiliar ─────────────────────────────────────────────
Q_NOM_AUX = 100.0
E_NOM_AUX = 1280.0
ALPHA_CF  = 0.98
G_CONST   = 9.81

AUX_OCV_TABLE = [
    (11.2, 0.0), (12.0, 5.0), (12.8, 10.0), (13.2, 20.0),
    (13.3, 40.0), (13.4, 60.0), (13.6, 80.0), (14.2, 95.0), (14.6, 100.0),
]

def ocv_to_soc_aux(v: float) -> float:
    if v <= AUX_OCV_TABLE[0][0]:  return 0.0
    if v >= AUX_OCV_TABLE[-1][0]: return 100.0
    for i in range(len(AUX_OCV_TABLE) - 1):
        v0, s0 = AUX_OCV_TABLE[i]
        v1, s1 = AUX_OCV_TABLE[i + 1]
        if v0 <= v <= v1:
            return s0 + (s1 - s0) * (v - v0) / (v1 - v0)
    return 0.0

# ─── Acumuladores por sesión (RAM) ────────────────────────────────────────────
_session_id_prev  = None
_E_HV             = 0.0
_Q_HV             = 0.0
_E_regen          = 0.0
_E_aux            = 0.0
_Q_aux            = 0.0
_soc0_aux         = None
_aux_muestras     = []
_aux_ultimo_t     = None

_v_rest_pack      = None
_v_rest_cells     = [None] * 16
_t_reposo_inicio  = None
_en_reposo        = False

_soh_c            = None
_soh_Q_SOH        = 0.0
_soh_soc_inicio   = None
_soh_t_ultimo     = None
_soh_activo       = False

_phi_rad   = 0.0
_theta_rad = 0.0

# ─── Línea de meta / conteo de vueltas (RAM) ─────────────────────────────────
_meta_xy          = None   # (xA, yA, xB, yB, lat_ref, lat_a, lon_a, lat_b, lon_b) o None
_meta_lock        = threading.Lock()
_sesion_act_prev  = False
_n_lap            = 0
_armado           = False   # primer cruce arma el cronómetro, no cuenta como vuelta
_laps_history     = []      # [{"n_lap":..,"t_vuelta":..,"d_vuelta":..}, ...] sesión actual
_t_vuelta_inicio  = None
_d_vuelta         = 0.0
_ultimo_gps       = None   # (x, y, d_signed, t)
_t_ultimo_cruce   = None
_d_ref_muestras   = []
_d_ref            = None

# ─── Cliente InfluxDB ─────────────────────────────────────────────────────────
influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api     = influx_client.write_api(write_options=SYNCHRONOUS)


# ─── Watchdog ─────────────────────────────────────────────────────────────────
def send_zero_snapshot():
    """Envía snapshot con todo en cero cuando no hay datos MQTT."""
    print("[WD] Sin datos MQTT — enviando snapshot cero", flush=True)
    ts_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    snapshot = {
        "timestamp":  ts_now,
        "vehicle_id": "25",
        "session_id": _session_id_prev or "0",
        "data": {
            "curr_rms": 0.0, "speed_v": 0.0,  "odo_veh":  0.0,
            "tmp_mot":  0.0, "tmp_cont": 0.0,  "tmp_cap":  0.0,
            "mot_torq": 0.0, "batt_curr": 0.0, "rpm":      0.0,
            "throttle": 0.0, "brake":    0.0,  "cont_st":  0.0,
            "ksy_v":    0.0, "volt_p":   0.0,  "curr_p":   0.0,
            "soc":      0.0, "tmp_max":  0.0,  "tmp_min":  0.0,
            "gps_lat":  0.0, "gps_lon":  0.0,
            "acc_x":    0.0, "acc_y":    0.0,  "acc_z":    0.0,
            "gyro_x":   0.0, "gyro_y":   0.0,  "gyro_z":   0.0,
            "volt_a":   0.0, "curr_a":   0.0,
            "cells": {f"cell_{i+1}": 0.0 for i in range(16)},
            "tau_est": 0.0, "p_mec": 0.0, "p_hv": None,
            "p_regen": None, "eta": None, "eta_bat": None, "eta_total": None,
            "E_HV":    round(_E_HV,    3),
            "Q_HV":    round(_Q_HV,    4),
            "E_regen": round(_E_regen, 3),
            "Q_HV_rest": 0.0, "E_HV_rest": 0.0,
            "r_pack": None,
            "r_cells": {f"r_cell_{i+1}": None for i in range(16)},
            "soh_c":   round(_soh_c, 2) if _soh_c is not None else None,
            "soh_activo": False, "soh_Q_SOH": 0.0, "soh_soc_inicio": None,
            "p_aux": 0.0,
            "E_aux": round(_E_aux, 3),
            "Q_aux": round(_Q_aux, 4),
            "soc_aux": None,
            "v_rest_pack": _v_rest_pack, "t_reposo_s": 0,
            "phi": 0.0, "theta": 0.0,
            "Gx":  0.0, "Gy":    0.0, "Gz": 0.0,
            "n_lap": _n_lap, "t_vuelta": 0.0, "d_vuelta": round(_d_vuelta, 4),
            "laps": list(_laps_history),
            "armado": False,
            "sesion_act": False,
            "meta_lat_a": _meta_xy[5] if _meta_xy else None,
            "meta_lon_a": _meta_xy[6] if _meta_xy else None,
            "meta_lat_b": _meta_xy[7] if _meta_xy else None,
            "meta_lon_b": _meta_xy[8] if _meta_xy else None,
        }
    }
    try:
        requests.post(API_INTERNAL_URL, json=snapshot, timeout=0.5)
    except Exception as e:
        print(f"[WD] Error POST: {e}", flush=True)


def reset_watchdog():
    """Reinicia el timer del watchdog. Llamar en cada on_message."""
    global _watchdog_timer
    if _watchdog_timer is not None:
        _watchdog_timer.cancel()
    _watchdog_timer = threading.Timer(WATCHDOG_TIMEOUT, send_zero_snapshot)
    _watchdog_timer.daemon = True
    _watchdog_timer.start()


# ─── Cálculo de variables derivadas ──────────────────────────────────────────
def compute_derived(data: dict, soc: float, curr_p: float) -> dict:
    global _phi_rad, _theta_rad

    curr_rms   = float(data.get("curr_rms", 0))
    rpm        = abs(float(data.get("rpm",  0)))
    volt_p     = float(data.get("volt_p",  0))
    cell_volts = data.get("cell_volts", [])

    tau_est = KT * curr_rms
    p_mec   = tau_est * (2 * math.pi * rpm / 60)
    p_hv    = (volt_p * abs(curr_p)) if curr_p < -I_MIN else None
    p_regen = (volt_p * curr_p)      if curr_p >  I_MIN else None

    if p_hv is not None and p_hv > 300:
        eta = min((p_mec / p_hv) * 100, 100.0)
    else:
        eta = None

    Q_HV_rest = Q_NOM * (soc / 100.0)
    E_HV_rest = E_NOM * (soc / 100.0)

    r_pack = None
    if _v_rest_pack is not None and abs(curr_p) > I_MIN:
        r_pack = (_v_rest_pack - volt_p) / abs(curr_p)

    # eta_bat: eficiencia batería (sag de voltaje vs. reposo)
    eta_bat = None
    if _v_rest_pack is not None and _v_rest_pack > 1:
        eta_bat = min((volt_p / _v_rest_pack) * 100, 100.0)

    # eta_total: eficiencia total del tren motriz (bat * motor)
    eta_total = None
    if eta is not None and eta_bat is not None:
        eta_total = (eta_bat * eta) / 100.0

    r_cells = {}
    for i, v_load in enumerate(cell_volts):
        v_rest = _v_rest_cells[i] if i < len(_v_rest_cells) else None
        if v_rest is not None and abs(curr_p) > I_MIN:
            r_cells[f"r_cell_{i+1}"] = round((v_rest - float(v_load)) / abs(curr_p), 8)
        else:
            r_cells[f"r_cell_{i+1}"] = None

    acc_x  = float(data.get("acc_x",  0))
    acc_y  = float(data.get("acc_y",  0))
    acc_z  = float(data.get("acc_z",  0))
    gyro_x = float(data.get("gyro_x", 0))
    gyro_y = float(data.get("gyro_y", 0))

    phi_acc   = math.atan2(acc_y, acc_z)
    theta_acc = math.atan2(-acc_x, math.sqrt(acc_y**2 + acc_z**2))

    phi_giro   = _phi_rad   + math.radians(gyro_x) * DT
    theta_giro = _theta_rad + math.radians(gyro_y) * DT

    _phi_rad   = ALPHA_CF * phi_giro   + (1 - ALPHA_CF) * phi_acc
    _theta_rad = ALPHA_CF * theta_giro + (1 - ALPHA_CF) * theta_acc

    phi_deg   = math.degrees(_phi_rad)
    theta_deg = math.degrees(_theta_rad)

    gx = -G_CONST * math.sin(_theta_rad)
    gy =  G_CONST * math.sin(_phi_rad) * math.cos(_theta_rad)
    gz =  G_CONST * math.cos(_phi_rad) * math.cos(_theta_rad)

    Gx = ((acc_x * G_CONST) - gx) / G_CONST
    Gy = ((acc_y * G_CONST) - gy) / G_CONST
    Gz = ((acc_z * G_CONST) - gz) / G_CONST

    return {
        "tau_est":    round(tau_est, 4),
        "p_mec":      round(p_mec,   2),
        "p_hv":       round(p_hv,    2) if p_hv    is not None else None,
        "p_regen":    round(p_regen, 2) if p_regen is not None else None,
        "eta":        round(eta,     2) if eta      is not None else None,
        "eta_bat":    round(eta_bat, 2) if eta_bat  is not None else None,
        "eta_total":  round(eta_total, 2) if eta_total is not None else None,
        "Q_HV_rest":  round(Q_HV_rest, 3),
        "E_HV_rest":  round(E_HV_rest, 2),
        "r_pack":     round(r_pack,  6) if r_pack  is not None else None,
        "r_cells":    r_cells,
        "phi":        round(phi_deg,   4),
        "theta":      round(theta_deg, 4),
        "Gx":         round(Gx, 4),
        "Gy":         round(Gy, 4),
        "Gz":         round(Gz, 4),
        "E_HV": None, "Q_HV": None, "E_regen": None, "soh_c": None,
        "p_aux": None, "E_aux": None, "Q_aux": None, "soc_aux": None,
    }


# ─── Conteo de vueltas ────────────────────────────────────────────────────────
def _to_xy(lat, lon, lat_ref_rad):
    """Proyección equirectangular simple lat/lon → km cartesianos locales."""
    x = EARTH_R_KM * math.radians(lon) * math.cos(lat_ref_rad)
    y = EARTH_R_KM * math.radians(lat)
    return x, y


def set_meta(lat_a, lon_a, lat_b, lon_b):
    """Setea/actualiza la línea de meta. No resetea n_lap — solo descarta
    la vuelta en curso y reinicia la espera de cruce contra la línea nueva."""
    global _meta_xy, _d_vuelta, _t_vuelta_inicio, _ultimo_gps, _t_ultimo_cruce

    lat_ref = math.radians((lat_a + lat_b) / 2.0)
    xA, yA  = _to_xy(lat_a, lon_a, lat_ref)
    xB, yB  = _to_xy(lat_b, lon_b, lat_ref)

    with _meta_lock:
        _meta_xy         = (xA, yA, xB, yB, lat_ref, lat_a, lon_a, lat_b, lon_b)
        _d_vuelta         = 0.0
        _t_vuelta_inicio  = None
        _ultimo_gps       = None
        _t_ultimo_cruce   = None

    print(f"[META] Línea de meta seteada — A=({lat_a},{lon_a}) B=({lat_b},{lon_b})", flush=True)


def reset_laps():
    """Reinicia el conteo de vueltas por completo. Se llama al detectar
    transición de sesión inactiva → activa."""
    global _n_lap, _d_vuelta, _t_vuelta_inicio, _ultimo_gps, _t_ultimo_cruce
    global _d_ref_muestras, _d_ref, _armado, _laps_history

    _n_lap            = 0
    _d_vuelta         = 0.0
    _t_vuelta_inicio  = None
    _ultimo_gps       = None
    _t_ultimo_cruce   = None
    _d_ref_muestras   = []
    _d_ref            = None
    _armado           = False
    _laps_history     = []
    print("[LAP] Conteo de vueltas reiniciado (nueva sesión activa)", flush=True)


def process_lap(gps_lat: float, gps_lon: float, speed_v: float, now_t: float, sesion_act: bool) -> dict:
    """Evalúa cruce de línea de meta y actualiza n_lap/t_vuelta/d_vuelta.
    El primer cruce válido arma el cronómetro (no cuenta como vuelta);
    los siguientes cierran vueltas. Si la sesión está inactiva o no hay
    línea seteada, congela el estado."""
    global _n_lap, _d_vuelta, _t_vuelta_inicio, _ultimo_gps, _t_ultimo_cruce
    global _d_ref_muestras, _d_ref, _armado, _laps_history

    if not sesion_act or _meta_xy is None:
        return {"n_lap": _n_lap, "t_vuelta": 0.0, "d_vuelta": round(_d_vuelta, 4), "laps": list(_laps_history), "armado": _armado}

    # GPS sin fix válido (0,0) — ignorar este snapshot para el conteo
    if gps_lat == 0.0 and gps_lon == 0.0:
        t_vuelta_actual = round(now_t - _t_vuelta_inicio, 1) if _t_vuelta_inicio else 0.0
        return {"n_lap": _n_lap, "t_vuelta": t_vuelta_actual, "d_vuelta": round(_d_vuelta, 4), "laps": list(_laps_history), "armado": _armado}

    xA, yA, xB, yB, lat_ref = _meta_xy[0], _meta_xy[1], _meta_xy[2], _meta_xy[3], _meta_xy[4]
    x, y = _to_xy(gps_lat, gps_lon, lat_ref)

    dx, dy   = xB - xA, yB - yA
    seg_len2 = dx * dx + dy * dy
    denom    = math.sqrt(seg_len2) if seg_len2 > 0 else 0.0
    d_signed = ((dx * (y - yA)) - (dy * (x - xA))) / denom if denom > 0 else 0.0

    if _t_vuelta_inicio is None:
        _t_vuelta_inicio = now_t

    _d_vuelta += abs(speed_v) * DT / 3600.0

    if _ultimo_gps is not None:
        x0, y0, d0, t0 = _ultimo_gps

        # ── Cambio de signo → candidato a cruce ──
        if d0 * d_signed < 0 and seg_len2 > 0:
            t_proj = ((x - xA) * dx + (y - yA) * dy) / seg_len2

            # ── Cruce dentro del segmento (no su extensión infinita) ──
            if 0.0 <= t_proj <= 1.0:
                debounce_ok = (_t_ultimo_cruce is None) or ((now_t - _t_ultimo_cruce) > LAP_DEBOUNCE)

                if debounce_ok:
                    # ── Interpolar instante exacto de cruce ──
                    frac = abs(d0) / (abs(d0) + abs(d_signed)) if (abs(d0) + abs(d_signed)) > 0 else 0.5
                    t_cruce = t0 + (now_t - t0) * frac

                    # ── Primer cruce: solo arma el cronómetro, no cuenta vuelta ──
                    if not _armado:
                        _armado          = True
                        _t_ultimo_cruce  = t_cruce
                        _t_vuelta_inicio = t_cruce
                        _d_vuelta        = 0.0
                        _ultimo_gps      = (x, y, d_signed, now_t)
                        print("[LAP] Primer cruce — cronómetro armado, esperando vuelta 1", flush=True)
                        return {"n_lap": _n_lap, "t_vuelta": 0.0, "d_vuelta": 0.0, "laps": list(_laps_history), "armado": _armado}

                    t_vuelta_actual = now_t - _t_vuelta_inicio
                    d_valida = True
                    if _d_ref is not None:
                        d_valida = (_d_ref * (1 - LAP_D_TOL)) <= _d_vuelta <= (_d_ref * (1 + LAP_D_TOL))

                    if t_vuelta_actual >= LAP_T_MIN and d_valida:
                        _n_lap += 1

                        # ── Calibración de distancia de referencia (primeras 5 vueltas) ──
                        if _d_ref is None:
                            _d_ref_muestras.append(_d_vuelta)
                            if len(_d_ref_muestras) >= LAP_N_CAL:
                                _d_ref = sum(_d_ref_muestras) / len(_d_ref_muestras)
                                print(f"[LAP] Calibración lista — d_ref={_d_ref:.3f} km", flush=True)

                        entry = {
                            "n_lap":    _n_lap,
                            "t_vuelta": round(t_vuelta_actual, 1),
                            "d_vuelta": round(_d_vuelta, 4),
                        }
                        _laps_history.append(entry)
                        print(f"[LAP] Vuelta {_n_lap} — t={t_vuelta_actual:.1f}s d={_d_vuelta:.3f}km", flush=True)

                        result = {**entry, "laps": list(_laps_history), "armado": _armado}

                        _t_ultimo_cruce  = t_cruce
                        _t_vuelta_inicio = t_cruce
                        _d_vuelta        = 0.0
                        _ultimo_gps      = (x, y, d_signed, now_t)
                        return result

    _ultimo_gps = (x, y, d_signed, now_t)
    t_vuelta_actual = round(now_t - _t_vuelta_inicio, 1) if _t_vuelta_inicio else 0.0
    return {"n_lap": _n_lap, "t_vuelta": t_vuelta_actual, "d_vuelta": round(_d_vuelta, 4), "laps": list(_laps_history), "armado": _armado}


# ─── Servidor HTTP interno: POST /set_meta ────────────────────────────────────
class _MetaHandler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, {})

    def do_POST(self):
        if self.path != "/set_meta":
            self._send(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body   = json.loads(self.rfile.read(length))
            lat_a  = float(body["lat_a"]); lon_a = float(body["lon_a"])
            lat_b  = float(body["lat_b"]); lon_b = float(body["lon_b"])
        except Exception:
            self._send(400, {"error": "json_invalido"})
            return

        if not (-90 <= lat_a <= 90 and -90 <= lat_b <= 90):
            self._send(400, {"error": "latitud_fuera_de_rango"}); return
        if not (-180 <= lon_a <= 180 and -180 <= lon_b <= 180):
            self._send(400, {"error": "longitud_fuera_de_rango"}); return
        if lat_a == lat_b and lon_a == lon_b:
            self._send(400, {"error": "PA_igual_a_PB"}); return

        set_meta(lat_a, lon_a, lat_b, lon_b)
        self._send(200, {"status": "ok", "lat_a": lat_a, "lon_a": lon_a, "lat_b": lat_b, "lon_b": lon_b})

    def log_message(self, fmt, *args):
        pass  # silenciar el log por request de http.server


def start_meta_server():
    server = ThreadingHTTPServer(("0.0.0.0", META_HTTP_PORT), _MetaHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f"[META] Servidor HTTP /set_meta escuchando en puerto {META_HTTP_PORT}", flush=True)


# ─── Callbacks MQTT ───────────────────────────────────────────────────────────
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("Conectado al broker MQTT")
        client.subscribe(MQTT_TOPIC)
        print(f"Suscrito a {MQTT_TOPIC}")
    else:
        print(f"Error de conexion MQTT: rc={rc}")

def on_message(client, userdata, msg):
    global _session_id_prev, _E_HV, _Q_HV, _E_regen, _E_aux, _Q_aux
    global _soc0_aux, _aux_muestras, _aux_ultimo_t
    global _v_rest_pack, _v_rest_cells, _t_reposo_inicio, _en_reposo
    global _soh_c, _soh_Q_SOH, _soh_soc_inicio, _soh_t_ultimo, _soh_activo
    global _phi_rad, _theta_rad
    global _sesion_act_prev

    # ── Watchdog: llegó un mensaje, reiniciar timer ───────────────────────────
    reset_watchdog()

    try:
        data = json.loads(msg.payload.decode())

        curr_p     = float(data.get("curr_p",  0))
        soc        = float(data.get("soc",     0))
        volt_p     = float(data.get("volt_p",  0))
        cell_volts = data.get("cell_volts", [])

        # ── 1. Detectar cambio de sesión (fecha + sess_id, evita choques entre días) ──
        fecha_hoy       = str(data.get("times", ""))[:10]
        new_session_id  = f"{fecha_hoy}_{data.get('sess_id', 0)}"
        if new_session_id != _session_id_prev:
            print(f"[Sesión] {_session_id_prev} → {new_session_id} — reiniciando acumuladores")
            _session_id_prev = new_session_id
            _E_HV = _Q_HV = _E_regen = _E_aux = _Q_aux = 0.0
            _soc0_aux = None; _aux_muestras = []; _aux_ultimo_t = None
            _soh_Q_SOH = 0.0; _soh_soc_inicio = None
            _soh_t_ultimo = None; _soh_activo = False
            _phi_rad = 0.0; _theta_rad = 0.0

        # ── 1b. Estado de sesión activa (lo calcula el MGT, no se infiere aquí) ──
        sesion_act = bool(data.get("sesion_act", False))
        if sesion_act and not _sesion_act_prev:
            reset_laps()
        _sesion_act_prev = sesion_act

        # ── 2. Lógica de reposo para V_rest ──────────────────────────────────
        now = time.time()
        if abs(curr_p) < I_MIN:
            if not _en_reposo:
                _en_reposo = True; _t_reposo_inicio = now
            else:
                if (now - _t_reposo_inicio) >= T_REPOSO:
                    _v_rest_pack  = volt_p
                    _v_rest_cells = [float(v) for v in cell_volts] if cell_volts else _v_rest_cells
        else:
            _en_reposo = False

        # ── 3. Calcular variables derivadas ───────────────────────────────────
        derived = compute_derived(data, soc, curr_p)

        # ── 3b. Conteo de vueltas ──────────────────────────────────────────────
        gps_lat  = float(data.get("gps_lat", 0))
        gps_lon  = float(data.get("gps_lon", 0))
        speed_v  = float(data.get("speed_v", 0))
        lap_info = process_lap(gps_lat, gps_lon, speed_v, now, sesion_act)
        derived["n_lap"]    = lap_info["n_lap"]
        derived["t_vuelta"] = lap_info["t_vuelta"]
        derived["d_vuelta"] = lap_info["d_vuelta"]
        derived["laps"]     = lap_info["laps"]
        derived["armado"]   = lap_info["armado"]

        # ── 4. Actualizar acumuladores HV ─────────────────────────────────────
        if curr_p < -I_MIN and derived["p_hv"] is not None:
            _E_HV += derived["p_hv"] * DT / 3600.0
        if curr_p < -I_MIN:
            _Q_HV += abs(curr_p) * DT / 3600.0
        if curr_p > I_MIN and derived["p_regen"] is not None:
            _E_regen += derived["p_regen"] * DT / 3600.0

        derived["E_HV"]    = round(_E_HV,    3)
        derived["Q_HV"]    = round(_Q_HV,    4)
        derived["E_regen"] = round(_E_regen, 3)

        # ── 5. Sistema auxiliar ───────────────────────────────────────────────
        volt_a = float(data.get("volt_a", 0))
        curr_a = float(data.get("curr_a", 0))
        p_aux  = volt_a * curr_a
        _E_aux += p_aux  * DT / 3600.0
        _Q_aux += curr_a * DT / 3600.0

        if _soc0_aux is None and len(_aux_muestras) < 4:
            if _aux_ultimo_t is None or (now - _aux_ultimo_t) >= 1.0:
                if curr_a > 0.0 and volt_a > 10.0:
                    _aux_muestras.append((curr_a, volt_a))
                    _aux_ultimo_t = now
                    print(f"[AUX] Muestra {len(_aux_muestras)}/4 — curr_a={curr_a:.2f}A volt_a={volt_a:.3f}V", flush=True)
                else:
                    print(f"[AUX] Muestra descartada — curr_a={curr_a:.2f}A volt_a={volt_a:.3f}V", flush=True)
                    _aux_ultimo_t = now
            if len(_aux_muestras) == 4:
                min_curr, volt_ocv = min(_aux_muestras, key=lambda x: x[0])
                _soc0_aux = ocv_to_soc_aux(volt_ocv)
                print(f"[AUX] SOC0 = {_soc0_aux:.1f}%", flush=True)

        soc_aux = max(0.0, _soc0_aux - (_Q_aux / Q_NOM_AUX) * 100.0) if _soc0_aux is not None else None
        derived["p_aux"]   = round(p_aux,   2)
        derived["E_aux"]   = round(_E_aux,  3)
        derived["Q_aux"]   = round(_Q_aux,  4)
        derived["soc_aux"] = round(soc_aux, 2) if soc_aux is not None else None

        # ── 6. Lógica SOH ─────────────────────────────────────────────────────
        if curr_p < -I_MIN:
            if not _soh_activo:
                _soh_activo = True; _soh_Q_SOH = 0.0; _soh_soc_inicio = soc
                print(f"[SOH] Inicio intervalo — SOC_inicio={soc:.1f}%", flush=True)
            elif _soh_soc_inicio is not None and _soh_soc_inicio < 1.0 and soc > 1.0:
                _soh_soc_inicio = soc; _soh_Q_SOH = 0.0
                print(f"[SOH] SOC_inicio corregido a {soc:.1f}%", flush=True)
            if _soh_t_ultimo is not None and (now - _soh_t_ultimo) > T_GAP_MAX:
                print(f"[SOH] Gap superado — reiniciando", flush=True)
                _soh_activo = False; _soh_Q_SOH = 0.0; _soh_soc_inicio = soc
            else:
                _soh_Q_SOH += abs(curr_p) * DT / 3600.0
            _soh_t_ultimo = now
            if _soh_soc_inicio is not None:
                delta_soc = _soh_soc_inicio - soc
                if delta_soc >= SOC_MIN_DELTA:
                    Q_teorico = Q_NOM * (delta_soc / 100.0)
                    _soh_c    = round((_soh_Q_SOH / Q_teorico) * 100.0, 2)
                    print(f"[SOH] SOH={_soh_c:.2f}%", flush=True)
                    _soh_activo = False; _soh_Q_SOH = 0.0; _soh_soc_inicio = None

        derived["soh_c"] = round(_soh_c, 2) if _soh_c is not None else None

        # ── 7. Escribir en InfluxDB ───────────────────────────────────────────
        ts = datetime.strptime(data["times"], "%Y-%m-%d %H:%M:%S.%f").replace(
            tzinfo=timezone(timedelta(hours=-6))
        )

        point = (
            Point("vehicle_telemetry")
            .tag("vehicle_id", str(data.get("veh_id", 25)))
            .tag("session_id",  str(data.get("sess_id", 0)))
            .tag("lap_number",  str(derived["n_lap"]))
            .time(ts, WritePrecision.MS)
            .field("curr_rms",  float(data.get("curr_rms",  0)))
            .field("speed_v",   float(data.get("speed_v",   0)))
            .field("odo_veh",   float(data.get("odo_veh",   0)))
            .field("tmp_mot",   float(data.get("tmp_mot",   0)))
            .field("tmp_cont",  float(data.get("tmp_cont",  0)))
            .field("tmp_cap",   float(data.get("tmp_cap",   0)))
            .field("mot_torq",  float(data.get("mot_torq",  0)))
            .field("batt_curr", float(data.get("batt_curr", 0)))
            .field("rpm",       float(data.get("rpm",       0)))
            .field("throttle",  float(data.get("throttle",  0)))
            .field("brake",     float(data.get("brake",     0)))
            .field("cont_st",   float(data.get("cont_st",   0)))
            .field("ksy_v",     float(data.get("ksy_v",     0)))
            .field("volt_p",    float(data.get("volt_p",    0)))
            .field("curr_p",    float(data.get("curr_p",    0)))
            .field("soc",       float(data.get("soc",       0)))
            .field("tmp_max",   float(data.get("tmp_max",   0)))
            .field("tmp_min",   float(data.get("tmp_min",   0)))
            .field("gps_lat",   float(data.get("gps_lat",   0)))
            .field("gps_lon",   float(data.get("gps_lon",   0)))
            .field("acc_x",     float(data.get("acc_x",     0)))
            .field("acc_y",     float(data.get("acc_y",     0)))
            .field("acc_z",     float(data.get("acc_z",     0)))
            .field("gyro_x",    float(data.get("gyro_x",    0)))
            .field("gyro_y",    float(data.get("gyro_y",    0)))
            .field("gyro_z",    float(data.get("gyro_z",    0)))
            .field("volt_a",    float(data.get("volt_a",    0)))
            .field("curr_a",    float(data.get("curr_a",    0)))
            .field("tau_est",   derived["tau_est"])
            .field("p_mec",     derived["p_mec"])
            .field("E_HV",      derived["E_HV"])
            .field("Q_HV",      derived["Q_HV"])
            .field("E_regen",   derived["E_regen"])
            .field("Q_HV_rest", derived["Q_HV_rest"])
            .field("E_HV_rest", derived["E_HV_rest"])
            .field("p_aux",     derived["p_aux"])
            .field("E_aux",     derived["E_aux"])
            .field("Q_aux",     derived["Q_aux"])
            .field("phi",       derived["phi"])
            .field("theta",     derived["theta"])
            .field("Gx",        derived["Gx"])
            .field("Gy",        derived["Gy"])
            .field("Gz",        derived["Gz"])
            .field("t_vuelta",  derived["t_vuelta"])
            .field("d_vuelta",  derived["d_vuelta"])
        )

        if derived["soc_aux"] is not None: point = point.field("soc_aux", derived["soc_aux"])
        if derived["p_hv"]    is not None: point = point.field("p_hv",    derived["p_hv"])
        if derived["p_regen"] is not None: point = point.field("p_regen", derived["p_regen"])
        if derived["eta"]     is not None: point = point.field("eta",     derived["eta"])
        if derived["eta_bat"]   is not None: point = point.field("eta_bat",   derived["eta_bat"])
        if derived["eta_total"] is not None: point = point.field("eta_total", derived["eta_total"])
        if derived["r_pack"]  is not None: point = point.field("r_pack",  derived["r_pack"])
        if derived["soh_c"]   is not None: point = point.field("soh_c",   derived["soh_c"])

        for i, v in enumerate(cell_volts):
            point = point.field(f"cell_{i+1}", float(v))
        for i in range(16):
            val = derived["r_cells"].get(f"r_cell_{i+1}")
            if val is not None: point = point.field(f"r_cell_{i+1}", val)

        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
        print(f"[InfluxDB] sess={data.get('sess_id')} t={data.get('times')} guardado")

        # ── 8. Empaquetar snapshot para fenix_api ─────────────────────────────
        snapshot = {
            "timestamp":  data.get("times"),
            "vehicle_id": str(data.get("veh_id", 25)),
            "session_id": str(data.get("sess_id", 0)),
            "data": {
                "curr_rms":  float(data.get("curr_rms",  0)),
                "speed_v":   float(data.get("speed_v",   0)),
                "odo_veh":   float(data.get("odo_veh",   0)),
                "tmp_mot":   float(data.get("tmp_mot",   0)),
                "tmp_cont":  float(data.get("tmp_cont",  0)),
                "tmp_cap":   float(data.get("tmp_cap",   0)),
                "mot_torq":  float(data.get("mot_torq",  0)),
                "batt_curr": float(data.get("batt_curr", 0)),
                "rpm":       float(data.get("rpm",       0)),
                "throttle":  float(data.get("throttle",  0)),
                "brake":     float(data.get("brake",     0)),
                "cont_st":   float(data.get("cont_st",   0)),
                "ksy_v":     float(data.get("ksy_v",     0)),
                "volt_p":    float(data.get("volt_p",    0)),
                "curr_p":    float(data.get("curr_p",    0)),
                "soc":       float(data.get("soc",       0)),
                "tmp_max":   float(data.get("tmp_max",   0)),
                "tmp_min":   float(data.get("tmp_min",   0)),
                "gps_lat":   float(data.get("gps_lat",   0)),
                "gps_lon":   float(data.get("gps_lon",   0)),
                "acc_x":     float(data.get("acc_x",     0)),
                "acc_y":     float(data.get("acc_y",     0)),
                "acc_z":     float(data.get("acc_z",     0)),
                "gyro_x":    float(data.get("gyro_x",    0)),
                "gyro_y":    float(data.get("gyro_y",    0)),
                "gyro_z":    float(data.get("gyro_z",    0)),
                "volt_a":    float(data.get("volt_a",    0)),
                "curr_a":    float(data.get("curr_a",    0)),
                "cells": {f"cell_{i+1}": float(v) for i, v in enumerate(cell_volts)},
                "tau_est":    derived["tau_est"],
                "p_mec":      derived["p_mec"],
                "p_hv":       derived["p_hv"],
                "p_regen":    derived["p_regen"],
                "eta":        derived["eta"],
                "eta_bat":    derived["eta_bat"],
                "eta_total":  derived["eta_total"],
                "E_HV":       derived["E_HV"],
                "Q_HV":       derived["Q_HV"],
                "E_regen":    derived["E_regen"],
                "Q_HV_rest":  derived["Q_HV_rest"],
                "E_HV_rest":  derived["E_HV_rest"],
                "r_pack":     derived["r_pack"],
                "r_cells":    derived["r_cells"],
                "soh_c":      derived["soh_c"],
                "soh_activo": _soh_activo,
                "soh_Q_SOH":  round(_soh_Q_SOH, 4),
                "soh_soc_inicio": _soh_soc_inicio,
                "p_aux":      derived["p_aux"],
                "E_aux":      derived["E_aux"],
                "Q_aux":      derived["Q_aux"],
                "soc_aux":    derived["soc_aux"],
                "v_rest_pack": _v_rest_pack,
                "t_reposo_s":  round(time.time() - _t_reposo_inicio, 1) if _en_reposo and _t_reposo_inicio else 0,
                "phi":        derived["phi"],
                "theta":      derived["theta"],
                "Gx":         derived["Gx"],
                "Gy":         derived["Gy"],
                "Gz":         derived["Gz"],
                "n_lap":      derived["n_lap"],
                "t_vuelta":   derived["t_vuelta"],
                "d_vuelta":   derived["d_vuelta"],
                "laps":       derived["laps"],
                "armado":     derived["armado"],
                "sesion_act": sesion_act,
                "meta_lat_a": _meta_xy[5] if _meta_xy else None,
                "meta_lon_a": _meta_xy[6] if _meta_xy else None,
                "meta_lat_b": _meta_xy[7] if _meta_xy else None,
                "meta_lon_b": _meta_xy[8] if _meta_xy else None,
            }
        }

        try:
            requests.post(API_INTERNAL_URL, json=snapshot, timeout=0.5)
        except Exception as api_err:
            print(f"[API push] {api_err}")

    except Exception as e:
        print(f"[ERROR on_message] {e}")


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect
    client.on_message = on_message

    start_meta_server()

    print("Conectando al broker MQTT...")
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)

    # Iniciar watchdog desde el arranque
    reset_watchdog()

    client.loop_forever()

if __name__ == "__main__":
    main()