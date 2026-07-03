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
MQTT_STATUS_TOPIC = "fenix/mgt/status"

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
_E_HV_lap_inicio     = 0.0
_E_regen_lap_inicio  = 0.0

# ─── Estado de conexión del MGT (via LWT) ────────────────────────────────────
_mgt_conectado = False
_last_snapshot = None   # dict completo {timestamp, vehicle_id, session_id, data} — último enviado

# ─── Cliente InfluxDB ─────────────────────────────────────────────────────────
influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api     = influx_client.write_api(write_options=SYNCHRONOUS)
query_api     = influx_client.query_api()


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
            "mgt_conectado": _mgt_conectado,
            "d_rest": None, "n_rest": None, "t_rest": None, "n_opt": None,
            "E_vuelta_actual": None, "E_regen_vuelta_actual": None,
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
    global _E_HV_lap_inicio, _E_regen_lap_inicio

    _n_lap            = 0
    _d_vuelta         = 0.0
    _t_vuelta_inicio  = None
    _ultimo_gps       = None
    _t_ultimo_cruce   = None
    _d_ref_muestras   = []
    _d_ref            = None
    _armado           = False
    _laps_history     = []
    _E_HV_lap_inicio     = 0.0
    _E_regen_lap_inicio  = 0.0
    print("[LAP] Conteo de vueltas reiniciado (nueva sesión activa)", flush=True)


# ─── Estimaciones de sesión: autonomía y vuelta óptima ───────────────────────
def compute_lap_estimates(laps_history: list, E_HV_rest) -> dict:
    """Calcula d_rest/n_rest/t_rest (autonomía estimada) y n_opt/score
    (vuelta óptima) a partir de las vueltas completadas de la sesión.
    Requiere al menos 1 vuelta con E_vuelta calculada; si no hay datos
    suficientes, devuelve None en los campos correspondientes."""
    completas = [l for l in laps_history if l.get("E_vuelta") is not None and l.get("d_vuelta", 0) > 0]

    d_rest = n_rest = t_rest = None
    if completas and E_HV_rest is not None:
        etas = [l["E_vuelta"] / l["d_vuelta"] for l in completas]
        eta_sesion_prom = sum(etas) / len(etas)
        d_sesion_prom   = sum(l["d_vuelta"] for l in completas) / len(completas)
        t_sesion_prom   = sum(l["t_vuelta"] for l in completas) / len(completas)

        if eta_sesion_prom > 0:
            d_rest = round(E_HV_rest / eta_sesion_prom, 2)
            if d_sesion_prom > 0:
                n_rest = round(d_rest / d_sesion_prom, 1)
                t_rest = round(n_rest * t_sesion_prom, 1)

    n_opt = None
    if len(completas) >= 2:
        t_mejor  = min(l["t_vuelta"] for l in completas)
        e_min    = min(l["E_vuelta"] for l in completas)
        if t_mejor > 0 and e_min > 0:
            mejor_score = None
            for l in completas:
                score = 0.5 * (l["t_vuelta"] / t_mejor) + 0.5 * (l["E_vuelta"] / e_min)
                if mejor_score is None or score < mejor_score:
                    mejor_score = score
                    n_opt = l["n_lap"]

    return {"d_rest": d_rest, "n_rest": n_rest, "t_rest": t_rest, "n_opt": n_opt}


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
                    else:
                        # ── Cruce rechazado: no cuenta como vuelta, pero SÍ se
                        # actualiza el debounce para no dejarlo "abierto" y que
                        # cruces espurios cercanos se sigan sin filtrar. El
                        # tiempo/distancia de la vuelta en curso NO se reinician,
                        # así el siguiente cruce válido mide correctamente. ──
                        motivo = "t_vuelta<{:.0f}s".format(LAP_T_MIN) if t_vuelta_actual < LAP_T_MIN else "distancia fuera de ±15% d_ref"
                        print(f"[LAP] Cruce RECHAZADO ({motivo}) — t={t_vuelta_actual:.1f}s d={_d_vuelta:.3f}km d_ref={_d_ref}", flush=True)
                        _t_ultimo_cruce = t_cruce

    _ultimo_gps = (x, y, d_signed, now_t)
    t_vuelta_actual = round(now_t - _t_vuelta_inicio, 1) if _t_vuelta_inicio else 0.0
    return {"n_lap": _n_lap, "t_vuelta": t_vuelta_actual, "d_vuelta": round(_d_vuelta, 4), "laps": list(_laps_history), "armado": _armado}


# ─── Servidor HTTP interno: POST /set_meta ────────────────────────────────────
# ─── Resumen y tabla de vueltas de sesiones históricas (consulta a InfluxDB) ──
def build_session_summary(date_str: str, session_id: str) -> dict:
    start = f"{date_str}T00:00:00Z"
    stop_dt = datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)
    stop = stop_dt.strftime("%Y-%m-%dT00:00:00Z")

    campos_base = ["soc", "E_HV", "Q_HV", "soc_aux", "E_aux", "Q_aux",
                   "speed_v", "rpm", "Gx", "Gy", "Gz", "p_hv", "p_regen",
                   "p_mec", "tmp_mot", "tmp_cont", "tmp_cap", "tmp_max", "curr_p"]
    filtro_campos = " or ".join([f'r._field == "{c}"' for c in campos_base])

    flux_base = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {start}, stop: {stop})
  |> filter(fn: (r) => r._measurement == "vehicle_telemetry" and r.session_id == "{session_id}")
  |> filter(fn: (r) => {filtro_campos})
  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"])
'''

    tables = query_api.query(flux_base, org=INFLUX_ORG)

    n = 0
    soc_ini = soc_fin = None
    ehv_ini = ehv_fin = qhv_ini = qhv_fin = None
    socaux_ini = socaux_fin = eaux_ini = eaux_fin = qaux_ini = qaux_fin = None
    spd_sum = spd_max = 0.0
    rpm_sum = rpm_max = 0.0
    gx_max = gy_max = gz_max = 0.0
    phv_sum = phv_max = phv_n = 0.0
    pregen_sum = pregen_max = pregen_n = 0.0
    pmec_sum = pmec_max = 0.0
    tmot_max = tcont_max = tcap_max = tbatt_max = 0.0
    currb_sum = currb_max = currb_n = 0.0
    currr_sum = currr_max = currr_n = 0.0
    t_ini = t_fin = None

    for table in tables:
        for rec in table.records:
            n += 1
            t = rec.get_time()
            if t_ini is None: t_ini = t
            t_fin = t

            def g(field):
                return rec.values.get(field)

            soc = g("soc")
            if soc is not None:
                if soc_ini is None: soc_ini = soc
                soc_fin = soc
            ehv = g("E_HV")
            if ehv is not None:
                if ehv_ini is None: ehv_ini = ehv
                ehv_fin = ehv
            qhv = g("Q_HV")
            if qhv is not None:
                if qhv_ini is None: qhv_ini = qhv
                qhv_fin = qhv
            socaux = g("soc_aux")
            if socaux is not None:
                if socaux_ini is None: socaux_ini = socaux
                socaux_fin = socaux
            eaux = g("E_aux")
            if eaux is not None:
                if eaux_ini is None: eaux_ini = eaux
                eaux_fin = eaux
            qaux = g("Q_aux")
            if qaux is not None:
                if qaux_ini is None: qaux_ini = qaux
                qaux_fin = qaux

            spd = g("speed_v")
            if spd is not None:
                spd_sum += spd; spd_max = max(spd_max, spd)
            rpm_v = g("rpm")
            if rpm_v is not None:
                rpm_v = abs(rpm_v)
                rpm_sum += rpm_v; rpm_max = max(rpm_max, rpm_v)
            gx=g("Gx"); gy=g("Gy"); gz=g("Gz")
            if gx is not None: gx_max = max(gx_max, abs(gx))
            if gy is not None: gy_max = max(gy_max, abs(gy))
            if gz is not None: gz_max = max(gz_max, abs(gz))
            phv = g("p_hv")
            if phv is not None:
                phv_sum += phv; phv_max = max(phv_max, phv); phv_n += 1
            pregen = g("p_regen")
            if pregen is not None:
                pregen_sum += pregen; pregen_max = max(pregen_max, pregen); pregen_n += 1
            pmec = g("p_mec")
            if pmec is not None:
                pmec_sum += pmec; pmec_max = max(pmec_max, pmec)
            for fld, acc in (("tmp_mot","tmot"),("tmp_cont","tcont"),("tmp_cap","tcap"),("tmp_max","tbatt")):
                v = g(fld)
                if v is not None:
                    if acc=="tmot": tmot_max = max(tmot_max, v)
                    elif acc=="tcont": tcont_max = max(tcont_max, v)
                    elif acc=="tcap": tcap_max = max(tcap_max, v)
                    else: tbatt_max = max(tbatt_max, v)
            curr_p = g("curr_p")
            if curr_p is not None:
                if curr_p < 0:
                    v = abs(curr_p); currb_sum += v; currb_max = max(currb_max, v); currb_n += 1
                elif curr_p > 0:
                    currr_sum += curr_p; currr_max = max(currr_max, curr_p); currr_n += 1

    dur_s = (t_fin - t_ini).total_seconds() if (t_ini and t_fin) else 0

    # ── Tabla de vueltas: agrupar por tag lap_number ──
    flux_laps = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {start}, stop: {stop})
  |> filter(fn: (r) => r._measurement == "vehicle_telemetry" and r.session_id == "{session_id}")
  |> filter(fn: (r) => r._field == "t_vuelta" or r._field == "d_vuelta" or r._field == "E_HV" or r._field == "E_regen")
  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"])
'''
    lap_tables = query_api.query(flux_laps, org=INFLUX_ORG)
    lap_groups = {}
    for table in lap_tables:
        for rec in table.records:
            lap_n = rec.values.get("lap_number")
            if lap_n is None: continue
            lap_n = int(lap_n)
            if lap_n == 0: continue
            grp = lap_groups.setdefault(lap_n, {"t":[], "d":[], "ehv":[], "ereg":[]})
            if rec.values.get("t_vuelta") is not None: grp["t"].append(rec.values["t_vuelta"])
            if rec.values.get("d_vuelta") is not None: grp["d"].append(rec.values["d_vuelta"])
            if rec.values.get("E_HV") is not None: grp["ehv"].append(rec.values["E_HV"])
            if rec.values.get("E_regen") is not None: grp["ereg"].append(rec.values["E_regen"])

    laps = []
    for lap_n in sorted(lap_groups.keys()):
        grp = lap_groups[lap_n]
        if not grp["t"] or not grp["d"]: continue
        t_v = max(grp["t"]); d_v = max(grp["d"])
        e_v = (max(grp["ehv"]) - min(grp["ehv"])) if grp["ehv"] else None
        er_v = (max(grp["ereg"]) - min(grp["ereg"])) if grp["ereg"] else None
        eta_v = round(e_v / d_v, 2) if (e_v is not None and d_v > 0) else None
        laps.append({
            "n_lap": lap_n, "t_vuelta": round(t_v, 1), "d_vuelta": round(d_v, 4),
            "E_vuelta": round(e_v, 3) if e_v is not None else None,
            "E_regen_vuelta": round(er_v, 3) if er_v is not None else None,
            "eta_vuelta": eta_v,
        })

    top_tiempo = sorted(laps, key=lambda l: l["t_vuelta"])[:3]
    con_e = [l for l in laps if l["E_vuelta"] is not None]
    top_consumo = sorted(con_e, key=lambda l: l["E_vuelta"])[:3]
    top_optimas = []
    if len(con_e) >= 2:
        t_mejor = min(l["t_vuelta"] for l in laps)
        e_min = min(l["E_vuelta"] for l in con_e)
        if t_mejor > 0 and e_min > 0:
            scored = [(0.5*(l["t_vuelta"]/t_mejor) + 0.5*(l["E_vuelta"]/e_min), l) for l in con_e]
            scored.sort(key=lambda x: x[0])
            top_optimas = [{"n_lap": l["n_lap"], "score": round(s,3)} for s,l in scored[:3]]

    e_vuelta_vals = [l["E_vuelta"] for l in laps if l["E_vuelta"] is not None]
    ereg_vuelta_vals = [l["E_regen_vuelta"] for l in laps if l["E_regen_vuelta"] is not None]

    return {
        "date": date_str, "session_id": session_id,
        "n_vueltas": len(laps), "duracion_s": round(dur_s, 0),
        "soc_ini": soc_ini, "soc_fin": soc_fin,
        "E_HV_ini": ehv_ini, "E_HV_fin": ehv_fin,
        "Q_HV_ini": qhv_ini, "Q_HV_fin": qhv_fin,
        "soc_aux_ini": socaux_ini, "soc_aux_fin": socaux_fin,
        "E_aux_ini": eaux_ini, "E_aux_fin": eaux_fin,
        "Q_aux_ini": qaux_ini, "Q_aux_fin": qaux_fin,
        "spd_prom": round(spd_sum/n, 1) if n else None, "spd_max": round(spd_max, 1),
        "rpm_prom": round(rpm_sum/n, 0) if n else None, "rpm_max": round(rpm_max, 0),
        "Gx_max": round(gx_max, 2), "Gy_max": round(gy_max, 2), "Gz_max": round(gz_max, 2),
        "p_hv_prom": round(phv_sum/phv_n, 1) if phv_n else None, "p_hv_max": round(phv_max, 1),
        "p_regen_prom": round(pregen_sum/pregen_n, 1) if pregen_n else None, "p_regen_max": round(pregen_max, 1),
        "p_mec_prom": round(pmec_sum/n, 1) if n else None, "p_mec_max": round(pmec_max, 1),
        "tmp_mot_max": round(tmot_max,1), "tmp_cont_max": round(tcont_max,1),
        "tmp_cap_max": round(tcap_max,1), "tmp_batt_max": round(tbatt_max,1),
        "curr_batt_prom": round(currb_sum/currb_n, 1) if currb_n else None, "curr_batt_max": round(currb_max, 1),
        "curr_regen_prom": round(currr_sum/currr_n, 1) if currr_n else None, "curr_regen_max": round(currr_max, 1),
        "E_vuelta_prom": round(sum(e_vuelta_vals)/len(e_vuelta_vals), 2) if e_vuelta_vals else None,
        "E_regen_vuelta_prom": round(sum(ereg_vuelta_vals)/len(ereg_vuelta_vals), 2) if ereg_vuelta_vals else None,
        "top_tiempo": top_tiempo, "top_consumo": top_consumo, "top_optimas": top_optimas,
        "laps": laps,
    }


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

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        if parsed.path != "/session_summary":
            self._send(404, {"error": "not_found"})
            return
        qs = parse_qs(parsed.query)
        date_str   = qs.get("date", [None])[0]
        session_id = qs.get("session_id", [None])[0]
        if not date_str or not session_id:
            self._send(400, {"error": "faltan_parametros_date_session_id"})
            return
        try:
            summary = build_session_summary(date_str, session_id)
        except Exception as e:
            self._send(500, {"error": str(e)})
            return
        self._send(200, summary)

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
        client.subscribe(MQTT_STATUS_TOPIC)
        print(f"Suscrito a {MQTT_TOPIC} y {MQTT_STATUS_TOPIC}")
    else:
        print(f"Error de conexion MQTT: rc={rc}")


def push_snapshot_now():
    """Reenvía el último snapshot conocido con el estado de conexión del MGT
    actualizado. Se usa cuando cambia sesion_act/LWT sin esperar el próximo dato."""
    global _last_snapshot
    if _last_snapshot is None:
        return
    snap = dict(_last_snapshot)
    snap["data"] = dict(snap["data"])
    snap["data"]["mgt_conectado"] = _mgt_conectado
    snap["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    try:
        requests.post(API_INTERNAL_URL, json=snap, timeout=0.5)
    except Exception as e:
        print(f"[MGT] Error POST estado: {e}", flush=True)


def on_status_message(msg):
    """Callback para el tópico fenix/mgt/status (LWT: 'online' / 'offline')."""
    global _mgt_conectado
    try:
        payload = msg.payload.decode().strip().lower()
    except Exception:
        payload = ""
    nuevo_estado = (payload == "online")
    if nuevo_estado != _mgt_conectado:
        _mgt_conectado = nuevo_estado
        print(f"[MGT] Estado → {'conectado' if _mgt_conectado else 'DESCONECTADO'}", flush=True)
        push_snapshot_now()


def on_message(client, userdata, msg):
    if msg.topic == MQTT_STATUS_TOPIC:
        on_status_message(msg)
        return
    on_snapshot_message(client, userdata, msg)


def on_snapshot_message(client, userdata, msg):
    global _session_id_prev, _E_HV, _Q_HV, _E_regen, _E_aux, _Q_aux
    global _soc0_aux, _aux_muestras, _aux_ultimo_t
    global _v_rest_pack, _v_rest_cells, _t_reposo_inicio, _en_reposo
    global _soh_c, _soh_Q_SOH, _soh_soc_inicio, _soh_t_ultimo, _soh_activo
    global _phi_rad, _theta_rad
    global _sesion_act_prev
    global _E_HV_lap_inicio, _E_regen_lap_inicio
    global _last_snapshot

    # ── Watchdog: llegó un mensaje, reiniciar timer ───────────────────────────
    reset_watchdog()

    try:
        data = json.loads(msg.payload.decode())

        # ── 0. Validar formato y campos obligatorios ──────────────────────────
        campos_obligatorios = ("veh_id", "sess_id", "times")
        faltantes = [c for c in campos_obligatorios if c not in data]
        if faltantes:
            print(f"[ERROR] Mensaje MQTT sin campos obligatorios: {faltantes}", flush=True)
            return

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
        n_lap_antes    = _n_lap
        armado_antes   = _armado
        lap_info = process_lap(gps_lat, gps_lon, speed_v, now, sesion_act)
        derived["n_lap"]    = lap_info["n_lap"]
        derived["t_vuelta"] = lap_info["t_vuelta"]
        derived["d_vuelta"] = lap_info["d_vuelta"]
        derived["laps"]     = lap_info["laps"]
        derived["armado"]   = lap_info["armado"]

        # ── Primer cruce (recién armado): marca el inicio de la vuelta 1 ───────
        if lap_info["armado"] and not armado_antes:
            _E_HV_lap_inicio    = _E_HV
            _E_regen_lap_inicio = _E_regen

        # ── Vuelta recién completada: energía consumida/regenerada en esa vuelta ──
        if lap_info["n_lap"] > n_lap_antes and _laps_history:
            e_vuelta       = round(_E_HV - _E_HV_lap_inicio, 3)
            e_regen_vuelta = round(_E_regen - _E_regen_lap_inicio, 3)
            _laps_history[-1]["E_vuelta"]       = e_vuelta
            _laps_history[-1]["E_regen_vuelta"] = e_regen_vuelta
            _laps_history[-1]["eta_vuelta"] = (
                round(e_vuelta / _laps_history[-1]["d_vuelta"], 2)
                if _laps_history[-1]["d_vuelta"] > 0 else None
            )
            derived["laps"] = list(_laps_history)
            _E_HV_lap_inicio    = _E_HV
            _E_regen_lap_inicio = _E_regen

        # ── Estimaciones de sesión: autonomía y vuelta óptima ──────────────────
        estim = compute_lap_estimates(_laps_history, derived.get("E_HV_rest"))
        derived.update(estim)

        # ── Energía de la vuelta en curso (se actualiza cada snapshot, no solo al cerrar) ──
        if lap_info["armado"]:
            derived["E_vuelta_actual"]       = round(_E_HV - _E_HV_lap_inicio, 3)
            derived["E_regen_vuelta_actual"] = round(_E_regen - _E_regen_lap_inicio, 3)
        else:
            derived["E_vuelta_actual"]       = None
            derived["E_regen_vuelta_actual"] = None

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
                "E_vuelta_actual":       derived["E_vuelta_actual"],
                "E_regen_vuelta_actual": derived["E_regen_vuelta_actual"],
                "d_rest":     derived["d_rest"],
                "n_rest":     derived["n_rest"],
                "t_rest":     derived["t_rest"],
                "n_opt":      derived["n_opt"],
                "sesion_act": sesion_act,
                "mgt_conectado": _mgt_conectado,
                "meta_lat_a": _meta_xy[5] if _meta_xy else None,
                "meta_lon_a": _meta_xy[6] if _meta_xy else None,
                "meta_lat_b": _meta_xy[7] if _meta_xy else None,
                "meta_lon_b": _meta_xy[8] if _meta_xy else None,
            }
        }

        _last_snapshot = snapshot
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