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

# ─── Constantes del motor ─────────────────────────────────────────────────────
KT = 0.143  # Nm/A — constante de torque ME MAX 6kW

# ─── Cliente InfluxDB ─────────────────────────────────────────────────────────
influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api     = influx_client.write_api(write_options=SYNCHRONOUS)

# ─── Cálculo de variables derivadas ──────────────────────────────────────────
def compute_derived(data: dict) -> dict:
    curr_rms = float(data.get("curr_rms", 0))
    rpm      = abs(float(data.get("rpm",      0)))  # siempre positivo
    volt_p   = float(data.get("volt_p",   0))
    curr_p   = float(data.get("curr_p",   0))

    # Torque estimado: τ_est = Kt × curr_rms [Nm]
    tau_est = KT * curr_rms

    # Potencia mecánica: P_mec = τ_est × (2π × rpm / 60) [W]
    p_mec = tau_est * (2 * math.pi * rpm / 60)

    # Potencia eléctrica HV: solo en descarga (curr_p < -5A), valor positivo
    p_hv = (volt_p * abs(curr_p)) if curr_p < -5.0 else None

    # Potencia regenerativa: válida solo cuando curr_p > 5A
    p_regen = (volt_p * curr_p) if curr_p > 5.0 else None

    # Eficiencia: válida solo cuando |P_HV| > 300W y curr_p < -5A (tracción real)
    if p_hv is not None and abs(p_hv) > 300:
        eta = (p_mec / abs(p_hv)) * 100
    else:
        eta = None

    return {
        "tau_est": round(tau_est, 4),
        "p_mec":   round(p_mec,   2),
        "p_hv":    round(p_hv,    2),
        "p_regen": round(p_regen, 2) if p_regen is not None else None,
        "eta":     round(eta,     2) if eta     is not None else None,
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
    try:
        data = json.loads(msg.payload.decode())

        # ── 1. Calcular variables derivadas ───────────────────────────────────
        derived = compute_derived(data)

        # ── 2. Guardar en InfluxDB ────────────────────────────────────────────
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
            .field("p_hv",      derived["p_hv"])
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

        # ── 3. Empaquetar snapshot para fenix_api ─────────────────────────────
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
                "tau_est":  derived["tau_est"],
                "p_mec":    derived["p_mec"],
                "p_hv":     derived["p_hv"],
                "p_regen":  derived["p_regen"],
                "eta":      derived["eta"],
            }
        }

        # ── 4. Empujar a fenix_api ────────────────────────────────────────────
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