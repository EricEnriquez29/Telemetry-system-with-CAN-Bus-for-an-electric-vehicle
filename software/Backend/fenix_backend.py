"""
fenix_backend.py  –  Escudería Fénix
- Escucha MQTT y guarda en InfluxDB
- Calcula variables derivadas del tren motriz
- Empuja cada snapshot a fenix_api via HTTP POST (RAM)
"""

import json
import math
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
KT    = 0.143    # Nm/A — constante de torque ME MAX 6kW
E_NOM = 5210.0   # Wh  — energía nominal paquete 16S LiFePO4 100Ah (52.1V × 100Ah)
Q_NOM = 100.0    # Ah  — capacidad nominal del paquete

# ─── Acumuladores por sesión (RAM) ────────────────────────────────────────────
_session_id_prev = None
_E_HV    = 0.0   # Wh — energía consumida acumulada
_Q_HV    = 0.0   # Ah — carga consumida acumulada
_E_regen = 0.0   # Wh — energía regenerada acumulada
DT       = 0.1   # s  — intervalo entre snapshots (10 Hz)

# ─── Cliente InfluxDB ─────────────────────────────────────────────────────────
influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api     = influx_client.write_api(write_options=SYNCHRONOUS)

# ─── Cálculo de variables derivadas ──────────────────────────────────────────
def compute_derived(data: dict, p_hv_val, p_regen_val, soc: float) -> dict:
    curr_rms = float(data.get("curr_rms", 0))
    rpm      = abs(float(data.get("rpm",      0)))
    volt_p   = float(data.get("volt_p",   0))
    curr_p   = float(data.get("curr_p",   0))

    # Torque estimado: τ_est = Kt × curr_rms [Nm]
    tau_est = KT * curr_rms

    # Potencia mecánica: P_mec = τ_est × (2π × rpm / 60) [W]
    p_mec = tau_est * (2 * math.pi * rpm / 60)

    # Potencia eléctrica HV: solo en descarga (curr_p < -5A), valor positivo
    p_hv = (volt_p * abs(curr_p)) if curr_p < -5.0 else None

    # Potencia regenerativa: solo en regen (curr_p > 5A)
    p_regen = (volt_p * curr_p) if curr_p > 5.0 else None

    # Eficiencia: válida solo cuando p_hv > 300W y curr_p < -5A
    if p_hv is not None and p_hv > 300:
        eta = (p_mec / p_hv) * 100
    else:
        eta = None

    # Capacidad y energía restante (instantáneas desde SOC del BMS)
    Q_HV_rest = Q_NOM * (soc / 100.0)
    E_HV_rest = E_NOM * (soc / 100.0)

    return {
        "tau_est":    round(tau_est, 4),
        "p_mec":      round(p_mec,   2),
        "p_hv":       round(p_hv,    2) if p_hv    is not None else None,
        "p_regen":    round(p_regen, 2) if p_regen is not None else None,
        "eta":        round(eta,     2) if eta      is not None else None,
        "Q_HV_rest":  round(Q_HV_rest, 3),
        "E_HV_rest":  round(E_HV_rest, 2),
        # Acumulativas — se actualizan en on_message
        "E_HV":    None,
        "Q_HV":    None,
        "E_regen": None,
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
    global _session_id_prev, _E_HV, _Q_HV, _E_regen
    try:
        data = json.loads(msg.payload.decode())

        # ── 1. Detectar cambio de sesión — reiniciar acumuladores ─────────────
        new_session_id = str(data.get("sess_id", 0))
        if new_session_id != _session_id_prev:
            print(f"[Sesión] Nueva sesión detectada: {_session_id_prev} → {new_session_id} — reiniciando acumuladores")
            _session_id_prev = new_session_id
            _E_HV    = 0.0
            _Q_HV    = 0.0
            _E_regen = 0.0

        # ── 2. Calcular variables derivadas ───────────────────────────────────
        curr_p = float(data.get("curr_p", 0))
        soc    = float(data.get("soc",    0))
        derived = compute_derived(data, None, None, soc)

        # ── 3. Actualizar acumuladores ────────────────────────────────────────
        # E_HV: solo en descarga (curr_p < -5A)
        if curr_p < -5.0 and derived["p_hv"] is not None:
            _E_HV += derived["p_hv"] * DT / 3600.0

        # Q_HV: solo en descarga (curr_p < -5A)
        if curr_p < -5.0:
            _Q_HV += abs(curr_p) * DT / 3600.0

        # E_regen: solo en regen (curr_p > 5A)
        if curr_p > 5.0 and derived["p_regen"] is not None:
            _E_regen += derived["p_regen"] * DT / 3600.0

        # Asignar acumuladores al derived
        derived["E_HV"]    = round(_E_HV,    3)
        derived["Q_HV"]    = round(_Q_HV,    4)
        derived["E_regen"] = round(_E_regen, 3)

        # ── 4. Guardar en InfluxDB ────────────────────────────────────────────
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
            # Variables derivadas
            .field("tau_est",   derived["tau_est"])
            .field("p_mec",     derived["p_mec"])
            .field("E_HV",      derived["E_HV"])
            .field("Q_HV",      derived["Q_HV"])
            .field("E_regen",   derived["E_regen"])
            .field("Q_HV_rest", derived["Q_HV_rest"])
            .field("E_HV_rest", derived["E_HV_rest"])
        )

        # Campos condicionales — solo se escriben si tienen valor
        if derived["p_regen"] is not None:
            point = point.field("p_regen", derived["p_regen"])
        if derived["eta"] is not None:
            point = point.field("eta",     derived["eta"])

        for i, v in enumerate(data.get("cell_volts", [])):
            point = point.field(f"cell_{i+1}", float(v))

        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
        print(f"[InfluxDB] sess={data.get('sess_id')} t={data.get('times')} guardado")

        # ── 5. Empaquetar snapshot para fenix_api ─────────────────────────────
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
                "cells": {f"cell_{i+1}": float(v)
                          for i, v in enumerate(data.get("cell_volts", []))},
                # Variables derivadas
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
            }
        }

        # ── 6. Empujar a fenix_api ────────────────────────────────────────────
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