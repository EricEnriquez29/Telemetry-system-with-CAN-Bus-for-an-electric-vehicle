# Módulos internos — Backend de Telemetría Fénix

**Escudería Fénix — UPIITA-IPN**
Ingeniería en Sistemas Automotrices

Carpeta: `software/Backend/backend_core/`

## Descripción

Este paquete contiene toda la lógica de `fenix_backend.py`, separada por responsabilidad. Antes vivía en un solo archivo de 1300+ líneas; aquí cada módulo sabe de una sola cosa, igual que en `Frontend/js/`. El punto de entrada real sigue siendo `../fenix_backend.py` — ese archivo solo importa `mqtt_listener.main` y lo ejecuta.

## Arquitectura (capas)

```
MQTT (broker) ──▶ mqtt_listener.py ──▶ fisica.py (cálculos puros)
                        │         ──▶ vueltas.py (conteo de vueltas)
                        │         ──▶ influx_client.py (guardar snapshot)
                        │         ──▶ requests → fenix_api.py (reenviar al Frontend)
                        ▼
                    estado.py (estado compartido de la sesión)

HTTP :8060 ──▶ meta_server.py ──▶ vueltas.py (setear línea de meta)
                                ──▶ historicos.py (consultar InfluxDB)
```

`mqtt_listener.py` y `meta_server.py` son los dos "controladores" (reciben entrada externa — MQTT o HTTP — y deciden qué hacer). `fisica.py`, `vueltas.py` e `historicos.py` son la lógica de negocio pura, sin saber de dónde vino el dato. `estado.py` y `config.py` son compartidos por todos.

## Archivos

**`config.py`** — se encarga de toda la configuración, mediante constantes de conexión (MQTT, InfluxDB), físicas del motor (KT, E_NOM, Q_NOM...) y conteo de vueltas. Los valores sensibles se leen de variables de entorno con default igual al valor histórico (ver `.env.example`). También configura el `logging` que usan los demás módulos.

**`estado.py`** — se encarga del estado que cambia mientras el backend corre, mediante una única instancia (`estado`) con atributos para: energía acumulada (HV y aux), salud de batería (SOH), voltajes en reposo, orientación IMU, línea de meta y conteo de vueltas. Reemplaza los ~45 `global _variable` que tenía el archivo original. Incluye `estado.lock` (`RLock`), que protege ese estado contra acceso concurrente entre el hilo de MQTT y los hilos HTTP de `meta_server.py`.

**`influx_client.py`** — se encarga del cliente de InfluxDB, mediante una sola instancia compartida (`write_api` para guardar, `query_api` para consultar) entre `mqtt_listener.py` e `historicos.py`.

**`fisica.py`** — se encarga de los cálculos físicos, mediante funciones puras (sin I/O):
- `compute_derived` — torque, potencias, eficiencias, resistencias internas, filtro complementario de orientación (roll/pitch).
- `ocv_to_soc_aux` — interpola el % de batería auxiliar por su voltaje.

**`vueltas.py`** — se encarga del conteo de vueltas, mediante:
- `process_lap` — detecta el cruce de la línea de meta por proyección GPS.
- `set_meta` — setea la línea de meta.
- `reset_laps` — reinicia el conteo al empezar sesión.
- `compute_lap_estimates` — calcula autonomía restante y vuelta óptima.

**`historicos.py`** — se encarga de sesiones pasadas, mediante consultas Flux a InfluxDB: `build_session_summary` arma el resumen completo (lo que pide el modal de históricos), `get_sessions_for_date` lista las sesiones de un día.

**`meta_server.py`** — se encarga de servir `/set_meta`, `/session_summary` y `/sessions_for_date` (puerto 8060), mediante validación del token de acceso y del formato de los parámetros *antes* de llamar a `vueltas.py`/`historicos.py` — nunca construye una consulta a InfluxDB directamente.

**`mqtt_listener.py`** — el orquestador: se encarga de recibir cada mensaje MQTT del MGT, mediante llamadas a `fisica.py` y `vueltas.py`, guardado en InfluxDB (`influx_client.py`) y reenvío a `fenix_api.py` por HTTP. También tiene el watchdog que envía un snapshot en ceros si deja de llegar telemetría. Toma `estado.lock` mientras procesa cada mensaje, y aísla la escritura a InfluxDB en su propio `try/except` para que un fallo ahí no bloquee el reenvío al Frontend.

## Convenciones

- **Sin variables globales sueltas**: todo el estado mutable vive en `estado.estado` (la instancia única de `EstadoBackend`); los módulos lo importan explícitamente (`from backend_core.estado import estado`) en vez de usar `global`.
- **Separación controlador / lógica / datos**: `mqtt_listener.py` y `meta_server.py` son los únicos que reciben entrada externa; `fisica.py`, `vueltas.py`, `historicos.py` no saben nada de MQTT ni de HTTP.
- **Validación de entrada en el borde**: `meta_server.py` valida formato de fecha/session_id y el token de acceso *antes* de pasarlos a la capa de InfluxDB — evita construir una consulta Flux con un valor no confiable.
- **Logging, no `print()`**: todos los mensajes usan `logging.getLogger(__name__)` en vez de `print(..., flush=True)`, configurado una sola vez en `config.py`.
- **Concurrencia**: `mqtt_listener.on_snapshot_message` y `vueltas.set_meta` toman `estado.lock` antes de tocar el estado compartido — necesario porque corren en hilos distintos (MQTT vs. HTTP de `meta_server.py`).
- **Fallos aislados**: cada operación externa que puede fallar de forma independiente (InfluxDB, el POST a `fenix_api.py`) tiene su propio `try/except`, para que un fallo no tumbe al resto del procesamiento del mensaje.
- **Nombres en español**, consistentes con el resto del proyecto (Frontend incluido).
- **Pruebas automatizadas**: `../test_automatizado.py` cubre `fisica.py`, `vueltas.py` y la validación de `meta_server.py` — ver "Pruebas automatizadas" en `../README.md`.
