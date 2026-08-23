# Backend de Telemetría — Escudería Fénix

**Escudería Fénix — UPIITA-IPN**
Ingeniería en Sistemas Automotrices
Sistema de Telemetría con CAN Bus para Vehículo Eléctrico

Carpeta: `software/Backend/`

## Descripción

Este es el backend que recibe la telemetría del vehículo por MQTT (enviada por el MGT, el gateway de telemetría montado en el karting), calcula las variables derivadas (potencias, eficiencias, orientación, conteo de vueltas), la guarda en InfluxDB, y la reenvía en tiempo real al [dashboard del Frontend](../Frontend/README.md) por WebSocket. También expone los endpoints HTTP que usa el Frontend para consultar sesiones históricas y setear la línea de meta.

Son **dos procesos independientes**:
- `fenix_backend.py` — el "cerebro": MQTT, cálculos, InfluxDB, conteo de vueltas, servidor de `/set_meta`.
- `fenix_api.py` — el "puente": recibe cada snapshot de `fenix_backend.py` por HTTP interno y lo reenvía por WebSocket a todos los dashboards conectados.

## Características

- Procesamiento en tiempo real de ~30 variables de telemetría a la frecuencia del MGT.
- Cálculo de eficiencia del tren motriz, potencia mecánica/eléctrica/regenerativa, resistencia interna del paquete y de cada celda.
- Filtro complementario (acelerómetro + giroscopio) para roll/pitch del vehículo.
- Conteo de vueltas por cruce de línea de meta (proyección GPS a coordenadas cartesianas locales, con calibración automática de distancia de referencia).
- Estimación de autonomía restante y vuelta más óptima (balance tiempo/consumo).
- Cálculo de salud de batería (SOH) por ciclos de descarga.
- Persistencia en InfluxDB de cada snapshot, con conteo de vuelta como tag.
- Consulta de sesiones históricas (resumen + tabla de vueltas) para el modal del Frontend.
- Watchdog: si el MGT deja de mandar datos, se envía un snapshot en ceros para que el dashboard no se quede "congelado" con el último valor real.
- Acceso concurrente protegido (`estado.lock`) entre el hilo de MQTT y los hilos HTTP de `/set_meta`.
- Si InfluxDB falla al escribir, la telemetría en vivo hacia el Frontend sigue funcionando igual (fallos aislados, ver Convenciones).

## Tecnologías utilizadas

| Tecnología | Uso |
|---|---|
| Python 3.11+ | Todo el backend |
| [paho-mqtt](https://pypi.org/project/paho-mqtt/) | Cliente MQTT (recibe telemetría del MGT) |
| [influxdb-client](https://pypi.org/project/influxdb-client/) | Escritura y consulta a InfluxDB (Flux) |
| [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) | `fenix_api.py`: servidor WebSocket/HTTP para el Frontend |
| [Pydantic](https://docs.pydantic.dev/) | Validación del payload que recibe `fenix_api.py` |
| [Requests](https://pypi.org/project/requests/) | `fenix_backend.py` → `fenix_api.py` (HTTP interno) |
| `http.server` (stdlib) | Servidor de `/set_meta`, `/session_summary`, `/sessions_for_date` |
| [pytest](https://pytest.org/) | Pruebas automatizadas (`test_automatizado.py`) |

## Estructura de la carpeta

```
software/Backend/
├── fenix_backend.py       Punto de entrada — arranca todo (ver backend_core/README.md)
├── fenix_api.py             Servidor WebSocket/HTTP para el Frontend (FastAPI)
├── test_automatizado.py       Pruebas automatizadas (pytest) — ver sección abajo
├── .env.example                 Plantilla de variables de entorno (copiar a .env)
└── backend_core/                  Módulos internos (ver backend_core/README.md)
    ├── __init__.py
    ├── config.py
    ├── estado.py
    ├── influx_client.py
    ├── fisica.py
    ├── vueltas.py
    ├── historicos.py
    ├── meta_server.py
    └── mqtt_listener.py
```

### `fenix_api.py`

**Se encarga de puente entre backend y Frontend**, mediante un servidor FastAPI aparte de `fenix_backend.py`:
- `POST /internal/snapshot` — `fenix_backend.py` empuja aquí cada snapshot ya procesado.
- `WS /ws` — el dashboard se conecta aquí; cada snapshot se reenvía a todos los clientes conectados.
- `GET /api/latest` — el último snapshot, por si algo necesita consultarlo por REST.

Se corre con: `uvicorn fenix_api:app --host 0.0.0.0 --port 8050`.

CORS es configurable por variable de entorno (`FENIX_ALLOWED_ORIGINS`, ver tabla abajo) — si no se define, acepta cualquier origen y lo avisa en el arranque.

## Arquitectura

```
MGT (vehículo) ──MQTT──▶ fenix_backend.py ──HTTP interno──▶ fenix_api.py ──WebSocket──▶ Frontend
                              │
                              ▼
                          InfluxDB
                              ▲
                              │ Flux queries
                     GET /session_summary
                     GET /sessions_for_date  ◀── Frontend (modal de históricos)
                     POST /set_meta          ◀── Frontend (formulario de línea de meta)
```

Ver `backend_core/README.md` para el detalle de capas dentro de `fenix_backend.py` (controlador → lógica de negocio → estado compartido).

## Requisitos para usar el sistema

- Python 3.11 o superior.
- Un broker MQTT accesible (por default `localhost:1883`) publicando en el tópico `fenix/mgt/snapshot` (y opcionalmente `fenix/mgt/status` para el LWT de conexión del MGT).
- Una instancia de InfluxDB accesible (por default `localhost:8086`) con el bucket configurado.
- `fenix_api.py` corriendo en el puerto 8050 (`fenix_backend.py` le empuja los snapshots).

### Instalación

```bash
cd software/Backend
pip install paho-mqtt influxdb-client requests fastapi uvicorn pydantic pytest
```

### Ejecutar

```bash
# Terminal 1 — servidor WebSocket/HTTP para el Frontend
uvicorn fenix_api:app --host 0.0.0.0 --port 8050

# Terminal 2 — backend principal (MQTT, cálculos, InfluxDB, /set_meta)
python fenix_backend.py
```

## Pruebas automatizadas

`test_automatizado.py` (pytest) cubre la lógica pura de `backend_core/`: fórmulas de `fisica.py`, conteo de vueltas de `vueltas.py`, y la validación de entrada de `meta_server.py` (formato de fecha/session_id, protección contra inyección en la consulta Flux). No requiere MQTT ni InfluxDB reales — corre en segundos, aislado.

**No cubre** `mqtt_listener.main()` ni `historicos.py` (necesitan un broker MQTT / InfluxDB real corriendo) — esas partes se siguen verificando a mano, con el sistema completo corriendo.

```bash
cd software/Backend
pytest -v
```

Correr esto antes de subir un cambio al servidor es la forma de detectar un error de lógica (por ejemplo en una fórmula de `fisica.py`) **antes** de que llegue a producción — no reemplaza probar con el vehículo real, es un primer filtro rápido y gratis.

## Dependencias

```
paho-mqtt
influxdb-client
requests
fastapi
uvicorn
pydantic
pytest       (solo para correr test_automatizado.py, no es necesario en producción)
```

## Configuración — variables de entorno

Los valores sensibles **no tienen default**: se leen del entorno y, si faltan, el backend arranca pero falla al conectarse. Es deliberado — antes estaban hardcodeados en `config.py`, visibles en el repositorio público.

Copia `.env.example` a `.env` y rellena los valores:

```bash
cd software/Backend
cp .env.example .env
nano .env
chmod 600 .env
```

El `.env` no se versiona (`.gitignore`). Para que los servicios lo lean, cada uno necesita esta línea bajo `[Service]`:

```
EnvironmentFile=/opt/fenix/software/Backend/.env
```

Sin ella el archivo existe pero nadie lo carga. Tras editarlo: `systemctl daemon-reload && systemctl restart fenix_backend fenix_api`.

| Variable | Default | Para qué es |
|---|---|---|
| `FENIX_MQTT_HOST` | `localhost` | Host del broker MQTT |
| `FENIX_MQTT_PORT` | `1883` | Puerto del broker MQTT |
| `FENIX_MQTT_USER` / `FENIX_MQTT_PASS` | **sin default** | Credenciales MQTT. Deben coincidir con `secrets.h` del firmware |
| `FENIX_INFLUX_URL` | `http://localhost:8086` | URL de InfluxDB |
| `FENIX_INFLUX_TOKEN` | **sin default** | Token de InfluxDB. Basta uno acotado a lectura/escritura del bucket |
| `FENIX_INFLUX_ORG` | `Escuderia Fenix UPIITA` | Organización en InfluxDB |
| `FENIX_INFLUX_BUCKET` | `Telemetria` | Bucket de InfluxDB |
| `FENIX_API_INTERNAL_URL` | `http://localhost:8050/internal/snapshot` | A dónde le empuja `fenix_backend.py` cada snapshot |
| `FENIX_META_HTTP_PORT` | `8060` | Puerto del servidor de `/set_meta` |
| `FENIX_META_TOKEN` | **sin default** | Token que valida `POST /set_meta` (lo envía el Frontend por header `X-Meta-Token`) |
| `FENIX_ALLOWED_ORIGINS` | *(vacío → `*`)* | Orígenes permitidos por CORS en `fenix_api.py`, separados por coma. **Vacío = abierto a cualquier origen** — defínelo con el dominio real del dashboard antes de producción. |

## Convenciones

- **Sin variables globales sueltas**: el estado mutable del backend vive en `backend_core/estado.py`, no como `global` sueltos por archivo.
- **Separación controlador / lógica de negocio**: solo `mqtt_listener.py` y `meta_server.py` reciben entrada externa (MQTT/HTTP); el resto son funciones puras o de acceso a datos.
- **Nunca secretos en el código**: contraseñas y tokens se leen de variables de entorno (ver arriba), sin default. Si falta una, el fallo es inmediato y visible — preferible a arrancar con una credencial hardcodeada.
- **Validación en el borde**: `meta_server.py` valida formato y autentica antes de tocar InfluxDB o el conteo de vueltas.
- **Logging, no `print()` suelto**: mensajes vía `logging`, mismo formato de tags (`[LAP]`, `[SOH]`, `[MGT]`, etc.) que antes.
- **Concurrencia controlada**: `estado.lock` (un `RLock`) protege el estado compartido entre el hilo de MQTT y los hilos HTTP de `meta_server.py` — evita que un `POST /set_meta` se mezcle con un mensaje MQTT a medio procesar.
- **Fallos aislados**: la escritura a InfluxDB tiene su propio `try/except` dentro de `mqtt_listener.py` — si InfluxDB está caído, se pierde ese punto histórico pero el dashboard en vivo sigue recibiendo datos igual.
- Ver también `backend_core/README.md` para las convenciones específicas de esos módulos.
