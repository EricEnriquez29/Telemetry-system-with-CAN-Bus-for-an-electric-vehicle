"""
fenix_backend.py  –  Escudería Fénix
- Escucha MQTT y guarda en InfluxDB
- Calcula variables derivadas del tren motriz
- Calcula orientación (Roll/Pitch) y aceleraciones compensadas (dinámica vehicular)
- Empuja cada snapshot a fenix_api via HTTP POST (RAM)
"""

import json
import math
import time
import requests
from datetime import datetime, timezone, timedelta
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
KT              = 0.143   # Nm/A — constante de torque ME MAX 6kW
E_NOM           = 5210.0  # Wh  — energía nominal 16S LiFePO4 100Ah
Q_NOM           = 100.0   # Ah  — capacidad nominal HV
I_MIN           = 10.0    # A   — umbral mínimo corriente
T_REPOSO        = 60.0    # s   — segundos en reposo para actualizar V_rest
T_GAP_MAX       = 600.0   # s   — gap máximo sin descarga para SOH (10 min)
SOC_MIN_DELTA   = 30.0    # %   — descarga mínima para calcular SOH
DT              = 0.1     # s   — intervalo entre snapshots (10 Hz)

# ─── Constantes batería auxiliar (LiFePO4 4S Humsienk 100Ah) ─────────────────
Q_NOM_AUX = 100.0   # Ah
E_NOM_AUX = 1280.0  # Wh (12.8V × 100Ah)

# ─── Constantes IMU ───────────────────────────────────────────────────────────
ALPHA_CF = 0.98   # Coeficiente filtro complementario
G_CONST  = 9.81   # m/s²

# Curva OCV vs SOC para LiFePO4 4S (celdas EVE 2.8V-3.65V)
AUX_OCV_TABLE = [
    (11.2, 0.0),
    (12.0, 5.0),
    (12.8, 10.0),
    (13.2, 20.0),
    (13.3, 40.0),
    (13.4, 60.0),
    (13.6, 80.0),
    (14.2, 95.0),
    (14.6, 100.0),
]

def ocv_to_soc_aux(v: float) -> float:
    """Interpola el SOC de la batería auxiliar dado su voltaje en circuito abierto."""
    if v <= AUX_OCV_TABLE[0][0]:
        return 0.0
    if v >= AUX_OCV_TABLE[-1][0]:
        return 100.0
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

# ─── Variables de reposo para resistencia interna (RAM) ──────────────────────
_v_rest_pack      = None
_v_rest_cells     = [None] * 16
_t_reposo_inicio  = None
_en_reposo        = False

# ─── Variables SOH (RAM) ─────────────────────────────────────────────────────
_soh_c            = None
_soh_Q_SOH        = 0.0
_soh_soc_inicio   = None
_soh_t_ultimo     = None
_soh_activo       = False

# ─── Variables filtro complementario IMU (RAM) ───────────────────────────────
_phi_rad   = 0.0   # Roll acumulado [rad]
_theta_rad = 0.0   # Pitch acumulado [rad]

# ─── Cliente InfluxDB ─────────────────────────────────────────────────────────
influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api     = influx_client.write_api(write_options=SYNCHRONOUS)


# ─── Cálculo de variables derivadas ──────────────────────────────────────────
def compute_derived(data: dict, soc: float, curr_p: float) -> dict:
    global _phi_rad, _theta_rad

    curr_rms   = float(data.get("curr_rms", 0))
    rpm        = abs(float(data.get("rpm",  0)))
    volt_p     = float(data.get("volt_p",  0))
    cell_volts = data.get("cell_volts", [])

    # ── Torque estimado ────────────────────────────────────────────────────
    tau_est = KT * curr_rms

    # ── Potencia mecánica ──────────────────────────────────────────────────
    p_mec = tau_est * (2 * math.pi * rpm / 60)

    # ── Potencia eléctrica HV (solo descarga) ─────────────────────────────
    p_hv = (volt_p * abs(curr_p)) if curr_p < -I_MIN else None

    # ── Potencia regenerativa (solo regen) ────────────────────────────────
    p_regen = (volt_p * curr_p) if curr_p > I_MIN else None

    # ── Eficiencia ────────────────────────────────────────────────────────
    if p_hv is not None and p_hv > 300:
        eta = min((p_mec / p_hv) * 100, 100.0)
    else:
        eta = None

    # ── Capacidad y energía restante ──────────────────────────────────────
    Q_HV_rest = Q_NOM * (soc / 100.0)
    E_HV_rest = E_NOM * (soc / 100.0)

    # ── Resistencia interna paquete ───────────────────────────────────────
    r_pack = None
    if _v_rest_pack is not None and abs(curr_p) > I_MIN:
        r_pack = (_v_rest_pack - volt_p) / abs(curr_p)

    # ── Resistencia interna por celda ─────────────────────────────────────
    r_cells = {}
    for i, v_load in enumerate(cell_volts):
        v_rest = _v_rest_cells[i] if i < len(_v_rest_cells) else None
        if v_rest is not None and abs(curr_p) > I_MIN:
            r_cells[f"r_cell_{i+1}"] = round((v_rest - float(v_load)) / abs(curr_p), 8)
        else:
            r_cells[f"r_cell_{i+1}"] = None

    # ── Orientación — filtro complementario ───────────────────────────────
    # El MPU-6050 entrega acc en g y gyro en °/s
    acc_x  = float(data.get("acc_x",  0))
    acc_y  = float(data.get("acc_y",  0))
    acc_z  = float(data.get("acc_z",  0))
    gyro_x = float(data.get("gyro_x", 0))
    gyro_y = float(data.get("gyro_y", 0))

    # Ángulos del acelerómetro [rad]
    phi_acc   = math.atan2(acc_y, acc_z)
    theta_acc = math.atan2(-acc_x, math.sqrt(acc_y**2 + acc_z**2))

    # Integración del giroscopio: gyro en °/s → rad/s → integrar con DT
    gyro_x_rad = math.radians(gyro_x)
    gyro_y_rad = math.radians(gyro_y)

    phi_giro   = _phi_rad   + gyro_x_rad * DT
    theta_giro = _theta_rad + gyro_y_rad * DT

    # Filtro complementario [rad]
    _phi_rad   = ALPHA_CF * phi_giro   + (1 - ALPHA_CF) * phi_acc
    _theta_rad = ALPHA_CF * theta_giro + (1 - ALPHA_CF) * theta_acc

    # Convertir a grados
    phi_deg   = math.degrees(_phi_rad)
    theta_deg = math.degrees(_theta_rad)

    # ── Aceleraciones compensadas por gravedad ────────────────────────────
    # acc_x/y/z viene en g → convertir a m/s² multiplicando por G_CONST
    # Calcular componente gravitacional proyectada en cada eje del vehículo
    gx = -G_CONST * math.sin(_theta_rad)
    gy =  G_CONST * math.sin(_phi_rad) * math.cos(_theta_rad)
    gz =  G_CONST * math.cos(_phi_rad) * math.cos(_theta_rad)

    # Aceleración dinámica real [m/s²]
    ax_veh = (acc_x * G_CONST) - gx
    ay_veh = (acc_y * G_CONST) - gy
    az_veh = (acc_z * G_CONST) - gz

    # Expresar en G (dividir entre 9.81)
    Gx = ax_veh / G_CONST
    Gy = ay_veh / G_CONST
    Gz = az_veh / G_CONST

    return {
        "tau_est":    round(tau_est, 4),
        "p_mec":      round(p_mec,   2),
        "p_hv":       round(p_hv,    2) if p_hv    is not None else None,
        "p_regen":    round(p_regen, 2) if p_regen is not None else None,
        "eta":        round(eta,     2) if eta      is not None else None,
        "Q_HV_rest":  round(Q_HV_rest, 3),
        "E_HV_rest":  round(E_HV_rest, 2),
        "r_pack":     round(r_pack,  6) if r_pack  is not None else None,
        "r_cells":    r_cells,
        # Orientación
        "phi":        round(phi_deg,   4),
        "theta":      round(theta_deg, 4),
        # Aceleraciones compensadas
        "Gx":         round(Gx, 4),
        "Gy":         round(Gy, 4),
        "Gz":         round(Gz, 4),
        # Acumulativas y SOH — se asignan en on_message
        "E_HV":    None,
        "Q_HV":    None,
        "E_regen": None,
        "soh_c":   None,
        # Auxiliar — se asignan en on_message
        "p_aux":      None,
        "E_aux":      None,
        "Q_aux":      None,
        "soc_aux":    None,
    }


# ─── Callbacks MQTT ───────────────────────────────────────────────────────────
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("Conectado al broker MQTT")
        client.subscribe(MQTT_TOPIC)
        print(f"Suscrito a {MQTT_TOPIC}")
    else:
        print(f"Error de conexion MQTT: rc={rc}")

def on_message(client, userdata, msg):
    global _session_id_prev, _E_HV, _Q_HV, _E_regen, _E_aux, _Q_aux, _soc0_aux, _aux_muestras, _aux_ultimo_t
    global _v_rest_pack, _v_rest_cells, _t_reposo_inicio, _en_reposo
    global _soh_c, _soh_Q_SOH, _soh_soc_inicio, _soh_t_ultimo, _soh_activo
    global _phi_rad, _theta_rad

    try:
        data = json.loads(msg.payload.decode())

        curr_p     = float(data.get("curr_p",  0))
        soc        = float(data.get("soc",     0))
        volt_p     = float(data.get("volt_p",  0))
        cell_volts = data.get("cell_volts", [])

        # ── 1. Detectar cambio de sesión ──────────────────────────────────────
        new_session_id = str(data.get("sess_id", 0))
        if new_session_id != _session_id_prev:
            print(f"[Sesión] {_session_id_prev} → {new_session_id} — reiniciando acumuladores")
            _session_id_prev = new_session_id
            _E_HV    = 0.0
            _Q_HV    = 0.0
            _E_regen = 0.0
            _E_aux        = 0.0
            _Q_aux        = 0.0
            _soc0_aux     = None
            _aux_muestras = []
            _aux_ultimo_t = None
            # Reiniciar SOH
            _soh_Q_SOH      = 0.0
            _soh_soc_inicio = None
            _soh_t_ultimo   = None
            _soh_activo     = False
            # Reiniciar filtro complementario IMU
            _phi_rad   = 0.0
            _theta_rad = 0.0

        # ── 2. Lógica de reposo para V_rest (60 segundos) ─────────────────────
        now = time.time()
        if abs(curr_p) < I_MIN:
            if not _en_reposo:
                _en_reposo        = True
                _t_reposo_inicio  = now
            else:
                if (now - _t_reposo_inicio) >= T_REPOSO:
                    _v_rest_pack  = volt_p
                    _v_rest_cells = [float(v) for v in cell_volts] if cell_volts else _v_rest_cells
        else:
            _en_reposo = False

        # ── 3. Calcular variables derivadas ───────────────────────────────────
        derived = compute_derived(data, soc, curr_p)

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

        # SOC0 auxiliar — 4 muestras a 1Hz, usar la de menor corriente
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
                print(f"[AUX] SOC0 = {_soc0_aux:.1f}% (volt_ocv={volt_ocv:.3f}V, curr_min={min_curr:.2f}A)", flush=True)

        if _soc0_aux is not None:
            soc_aux = max(0.0, _soc0_aux - (_Q_aux / Q_NOM_AUX) * 100.0)
        else:
            soc_aux = None

        derived["p_aux"]   = round(p_aux,   2)
        derived["E_aux"]   = round(_E_aux,  3)
        derived["Q_aux"]   = round(_Q_aux,  4)
        derived["soc_aux"] = round(soc_aux, 2) if soc_aux is not None else None

        # ── 6. Lógica SOH ─────────────────────────────────────────────────────
        if curr_p < -I_MIN:
            if not _soh_activo:
                _soh_activo     = True
                _soh_Q_SOH      = 0.0
                _soh_soc_inicio = soc
                print(f"[SOH] Inicio intervalo — SOC_inicio={soc:.1f}%", flush=True)
            elif _soh_soc_inicio is not None and _soh_soc_inicio < 1.0 and soc > 1.0:
                _soh_soc_inicio = soc
                _soh_Q_SOH      = 0.0
                print(f"[SOH] SOC_inicio corregido a {soc:.1f}%", flush=True)

            if _soh_t_ultimo is not None and (now - _soh_t_ultimo) > T_GAP_MAX:
                print(f"[SOH] Gap de {now - _soh_t_ultimo:.0f}s superado — reiniciando", flush=True)
                _soh_activo     = False
                _soh_Q_SOH      = 0.0
                _soh_soc_inicio = soc
            else:
                _soh_Q_SOH += abs(curr_p) * DT / 3600.0

            _soh_t_ultimo = now

            if _soh_soc_inicio is not None:
                delta_soc = _soh_soc_inicio - soc
                if delta_soc >= SOC_MIN_DELTA:
                    Q_teorico = Q_NOM * (delta_soc / 100.0)
                    _soh_c    = round((_soh_Q_SOH / Q_teorico) * 100.0, 2)
                    print(f"[SOH] Calculado — ΔSoC={delta_soc:.1f}% Q_real={_soh_Q_SOH:.3f}Ah Q_teo={Q_teorico:.3f}Ah SOH={_soh_c:.2f}%", flush=True)
                    _soh_activo     = False
                    _soh_Q_SOH      = 0.0
                    _soh_soc_inicio = None

        derived["soh_c"] = round(_soh_c, 2) if _soh_c is not None else None

        # ── 7. Escribir en InfluxDB ───────────────────────────────────────────
        ts = datetime.strptime(data["times"], "%Y-%m-%d %H:%M:%S.%f").replace(
            tzinfo=timezone(timedelta(hours=-6))
        )

        point = (
            Point("vehicle_telemetry")
            .tag("vehicle_id", str(data.get("veh_id", 25)))
            .tag("session_id",  str(data.get("sess_id", 0)))
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
            # Derivadas siempre presentes
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
            # Orientación y aceleraciones compensadas
            .field("phi",       derived["phi"])
            .field("theta",     derived["theta"])
            .field("Gx",        derived["Gx"])
            .field("Gy",        derived["Gy"])
            .field("Gz",        derived["Gz"])
        )

        if derived["soc_aux"] is not None:
            point = point.field("soc_aux", derived["soc_aux"])

        # Campos condicionales
        if derived["p_hv"]    is not None: point = point.field("p_hv",    derived["p_hv"])
        if derived["p_regen"] is not None: point = point.field("p_regen", derived["p_regen"])
        if derived["eta"]     is not None: point = point.field("eta",     derived["eta"])
        if derived["r_pack"]  is not None: point = point.field("r_pack",  derived["r_pack"])
        if derived["soh_c"]   is not None: point = point.field("soh_c",   derived["soh_c"])

        for i, v in enumerate(cell_volts):
            point = point.field(f"cell_{i+1}", float(v))

        for i in range(16):
            key = f"r_cell_{i+1}"
            val = derived["r_cells"].get(key)
            if val is not None:
                point = point.field(key, val)

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
                # Derivadas tren motriz
                "tau_est":    derived["tau_est"],
                "p_mec":      derived["p_mec"],
                "p_hv":       derived["p_hv"],
                "p_regen":    derived["p_regen"],
                "eta":        derived["eta"],
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
                # Auxiliar
                "p_aux":      derived["p_aux"],
                "E_aux":      derived["E_aux"],
                "Q_aux":      derived["Q_aux"],
                "soc_aux":    derived["soc_aux"],
                # Reposo
                "v_rest_pack": _v_rest_pack,
                "t_reposo_s":  round(time.time() - _t_reposo_inicio, 1) if _en_reposo and _t_reposo_inicio else 0,
                # Orientación y aceleraciones compensadas
                "phi":        derived["phi"],
                "theta":      derived["theta"],
                "Gx":         derived["Gx"],
                "Gy":         derived["Gy"],
                "Gz":         derived["Gz"],
            }
        }

        # ── 9. Empujar a fenix_api ────────────────────────────────────────────
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

    print("Conectando al broker MQTT...")
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_forever()

if __name__ == "__main__":
    main()