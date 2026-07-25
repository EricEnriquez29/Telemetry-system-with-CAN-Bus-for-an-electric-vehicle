"""
influx_client.py — Cliente único de InfluxDB, compartido por mqtt_listener.py
(para escribir cada snapshot) y historicos.py (para consultar sesiones
pasadas). Antes cada módulo hubiera necesitado crear su propio cliente;
aquí se crea una sola vez y se reutiliza.
"""

from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS

from backend_core import config

influx_client = InfluxDBClient(
    url=config.INFLUX_URL, token=config.INFLUX_TOKEN, org=config.INFLUX_ORG
)
write_api = influx_client.write_api(write_options=SYNCHRONOUS)
query_api = influx_client.query_api()
