"""
config.py — Configuración central de fenix_backend.

Todos los valores sensibles (contraseñas, tokens) se leen de variables de
entorno con `os.environ.get(NOMBRE, default)`. El default es el valor
histórico que ya usaba el equipo, para que el backend siga funcionando
igual si nadie define las variables de entorno — pero ahora SÍ se puede
sobreescribir cada uno sin tocar código (ver README.md para la lista de
variables de entorno soportadas).
"""

import logging
import os

# ─── Logging ───────────────────────────────────────────────────────────────
# Reemplaza los print() sueltos que había en el archivo original por un
# logger estándar; el formato de mensaje se mantiene igual (mismos tags
# [LAP]/[SOH]/[AUX]/[META]/[MGT]/[WD]) para no cambiar lo que ve el equipo
# en consola durante una carrera.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
)

# ─── MQTT ────────────────────────────────────────────────────────────────
MQTT_HOST = os.environ.get("FENIX_MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("FENIX_MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("FENIX_MQTT_USER", "fenix25")
MQTT_PASS = os.environ.get("FENIX_MQTT_PASS", "pswTeleFenix")
MQTT_TOPIC = "fenix/mgt/snapshot"
MQTT_STATUS_TOPIC = "fenix/mgt/status"

# ─── InfluxDB ────────────────────────────────────────────────────────────
INFLUX_URL = os.environ.get("FENIX_INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.environ.get(
    "FENIX_INFLUX_TOKEN",
    "LIYzY_Q_DaHCXNDQ3fpkfnTxh9Lx_-wITjXy-3jlGyccx0LpB0yozjM-dpVf6_0YMHjZxS7m4ZTvG7wHVtzrjg==",
)
INFLUX_ORG = os.environ.get("FENIX_INFLUX_ORG", "Escuderia Fenix UPIITA")
INFLUX_BUCKET = os.environ.get("FENIX_INFLUX_BUCKET", "Telemetria")

# ─── URL interna de fenix_api ────────────────────────────────────────────
API_INTERNAL_URL = os.environ.get(
    "FENIX_API_INTERNAL_URL", "http://localhost:8050/internal/snapshot"
)

# ─── Constantes del motor y paquete ──────────────────────────────────────
KT = 0.143
E_NOM = 5210.0
Q_NOM = 100.0
I_MIN = 10.0
T_REPOSO = 60.0
T_GAP_MAX = 600.0
SOC_MIN_DELTA = 30.0
DT = 0.1

# ─── Constantes conteo de vueltas ────────────────────────────────────────
LAP_DEBOUNCE = 10.0  # s mínimos entre dos cruces válidos
LAP_T_MIN = 15.0     # s mínimos de duración de una vuelta — FIJO, no cambiar sin que Payo lo pida
TZ_OFFSET_HOURS = 6  # México Centro (UTC-6). Medianoche local = 06:00 UTC.
LAP_N_CAL = 5        # vueltas usadas para calibrar la distancia de referencia
LAP_D_TOL = 0.15     # tolerancia ±15% sobre la distancia de referencia
EARTH_R_KM = 6371.0
META_HTTP_PORT = int(os.environ.get("FENIX_META_HTTP_PORT", "8060"))

# ─── Token de acceso para /set_meta ──────────────────────────────────────
# Antes se validaba una contraseña hardcodeada en el frontend (visible en
# el código fuente del navegador). Ahora la validación real ocurre en el
# backend (meta_server.py), comparando este token contra el header
# X-Meta-Token — el frontend nunca lo compara localmente.
META_ACCESS_TOKEN = os.environ.get("FENIX_META_TOKEN", "fenix25")

# ─── Watchdog ─────────────────────────────────────────────────────────────
WATCHDOG_TIMEOUT = 5.0  # segundos sin datos MQTT → enviar ceros

# ─── Constantes batería auxiliar ─────────────────────────────────────────
Q_NOM_AUX = 100.0
E_NOM_AUX = 1280.0
ALPHA_CF = 0.98
G_CONST = 9.81

AUX_OCV_TABLE = [
    (11.2, 0.0), (12.0, 5.0), (12.8, 10.0), (13.2, 20.0),
    (13.3, 40.0), (13.4, 60.0), (13.6, 80.0), (14.2, 95.0), (14.6, 100.0),
]
