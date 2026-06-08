import json
from datetime import datetime, timezone
import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# ─── Configuración MQTT ───────────────────────────────────────────────────────
MQTT_HOST    = "localhost"
MQTT_PORT    = 1883
MQTT_USER    = "fenix25"
MQTT_PASS    = "pswTeleFenix"
MQTT_TOPIC   = "fenix/mgt/snapshot"

# ─── Configuración InfluxDB ───────────────────────────────────────────────────
INFLUX_URL    = "http://localhost:8086"
INFLUX_TOKEN  = "LIYzY_Q_DaHCXNDQ3fpkfnTxh9Lx_-wITjXy-3jlGyccx0LpB0yozjM-dpVf6_0YMHjZxS7m4ZTvG7wHVtzrjg=="
INFLUX_ORG    = "Escuderia Fenix UPIITA"
INFLUX_BUCKET = "Telemetria"

# ─── Cliente InfluxDB ─────────────────────────────────────────────────────────
influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api     = influx_client.write_api(write_options=SYNCHRONOUS)

# ─── Callback MQTT ────────────────────────────────────────────────────────────
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("Conectado al broker MQTT")
        client.subscribe(MQTT_TOPIC)
        print(f"Suscrito a {MQTT_TOPIC}")
    else:
        print(f"Error de conexion: {rc}")

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())

        # Parsear timestamp
        ts = datetime.strptime(data["times"], "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)

        # Construir punto InfluxDB
        point = (
            Point("vehicle_telemetry")
            .tag("vehicle_id", str(data.get("veh_id", 25)))
            .tag("session_id",  str(data.get("sess_id", 0)))
            .time(ts, WritePrecision.MS)
            .field("curr_rms",   float(data.get("curr_rms",  0)))
            .field("speed_v",    float(data.get("speed_v",   0)))
            .field("odo_veh",    float(data.get("odo_veh",   0)))
            .field("tmp_mot",    float(data.get("tmp_mot",   0)))
            .field("tmp_cont",   float(data.get("tmp_cont",  0)))
            .field("tmp_cap",    float(data.get("tmp_cap",   0)))
            .field("mot_torq",   float(data.get("mot_torq",  0)))
            .field("batt_curr",  float(data.get("batt_curr", 0)))
            .field("rpm",        float(data.get("rpm",       0)))
            .field("throttle",   float(data.get("throttle",  0)))
            .field("brake",      float(data.get("brake",     0)))
            .field("cont_st",    float(data.get("cont_st",   0)))
            .field("ksy_v",      float(data.get("ksy_v",     0)))
            .field("volt_p",     float(data.get("volt_p",    0)))
            .field("curr_p",     float(data.get("curr_p",    0)))
            .field("soc",        float(data.get("soc",       0)))
            .field("tmp_max",    float(data.get("tmp_max",   0)))
            .field("tmp_min",    float(data.get("tmp_min",   0)))
            .field("gps_lat",    float(data.get("gps_lat",   0)))
            .field("gps_lon",    float(data.get("gps_lon",   0)))
            .field("acc_x",      float(data.get("acc_x",     0)))
            .field("acc_y",      float(data.get("acc_y",     0)))
            .field("acc_z",      float(data.get("acc_z",     0)))
            .field("gyro_x",     float(data.get("gyro_x",    0)))
            .field("gyro_y",     float(data.get("gyro_y",    0)))
            .field("gyro_z",     float(data.get("gyro_z",    0)))
            .field("volt_a",     float(data.get("volt_a",    0)))
            .field("curr_a",     float(data.get("curr_a",    0)))
        )

        # Celdas de voltaje
        cell_volts = data.get("cell_volts", [])
        for i, v in enumerate(cell_volts):
            point = point.field(f"cell_{i+1}", float(v))

        # Escribir en InfluxDB
        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
        print(f"[DB] sess={data.get('sess_id')} t={data.get('times')} spd={data.get('speed_v')}")

    except Exception as e:
        print(f"[ERROR] {e}")

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