# Software — Sistema de Telemetría Fénix

**Escudería Fénix — UPIITA-IPN**
Ingeniería en Sistemas Automotrices
Sistema de Telemetría con CAN Bus para Vehículo Eléctrico

Carpeta: `software/`

## Descripción

Esta carpeta contiene las dos mitades del sistema de telemetría que corren fuera del vehículo: el **Backend** (recibe, procesa y guarda los datos que manda el MGT) y el **Frontend** (el dashboard web donde el equipo ve esos datos en tiempo real), más `deploy/` con los archivos systemd que los mantienen corriendo en el servidor. El firmware que corre dentro del vehículo vive en `../firmware/`, fuera del alcance de esta carpeta.

## Estructura

```
software/
├── Backend/     Procesa la telemetría, la guarda y la reenvía — ver Backend/README.md
├── Frontend/    Dashboard web que muestra la telemetría en vivo — ver Frontend/README.md
└── deploy/      Los tres .service de systemd que corren todo esto — ver deploy/README.md
```

### `Backend/`

**Se encarga de todo lo que pasa entre el vehículo y el dashboard**, mediante dos procesos Python (`fenix_backend.py` y `fenix_api.py`): recibe la telemetría por MQTT, calcula variables derivadas (potencias, eficiencias, orientación), cuenta vueltas por GPS, guarda todo en InfluxDB, y lo reenvía al Frontend por WebSocket. También expone los endpoints HTTP para consultar sesiones históricas y setear la línea de meta.

Empieza en [`Backend/README.md`](Backend/README.md) — ahí está la arquitectura completa, cómo instalarlo/correrlo, variables de entorno y las pruebas automatizadas. El detalle módulo por módulo está en [`Backend/backend_core/README.md`](Backend/backend_core/README.md).

### `Frontend/`

**Se encarga de mostrar esa telemetría en un dashboard web**, mediante HTML/CSS/JS vanilla (sin framework): gauges, gráficas en tiempo real, mapa GPS, tabla de vueltas, modelo 3D del vehículo, y el modal de sesiones históricas — todo alimentado por la conexión WebSocket al Backend.

Empieza en [`Frontend/README.md`](Frontend/README.md) — ahí está la arquitectura, tecnologías, requisitos, y cómo se conecta con el Backend. El detalle de cada hoja de estilo está en [`Frontend/css/README.md`](Frontend/css/README.md), y el de cada script en [`Frontend/js/README.md`](Frontend/js/README.md).

### `deploy/`

**Se encarga de que los dos procesos de arriba sigan corriendo en el servidor**, mediante tres unidades de systemd: una por cada proceso del Backend y otra para servir el Frontend. Son copia de los que están instalados en `/etc/systemd/system/`, versionados aquí para poder reinstalar o migrar el servidor sin reescribirlos de memoria.

Empieza en [`deploy/README.md`](deploy/README.md) — ahí está qué asume cada archivo, cómo montar un servidor desde cero, y las dos trampas del despliegue (hacer el `git pull` como el usuario `fenix`, y que sin `systemctl restart` el pull no surte efecto).

## Cómo se relacionan

```
Vehículo (MGT) --MQTT--> Backend --WebSocket/HTTP--> Frontend (navegador del equipo)
```

El Backend no sabe nada de HTML/CSS — solo expone datos en JSON. El Frontend no sabe nada de MQTT/InfluxDB — solo consume esos datos. Se pueden desarrollar y probar por separado (el Frontend tiene un simulador aparte para probar sin el Backend corriendo — ver `Frontend/README.md`).

## Pruebas automatizadas

Ambas carpetas tienen su propio archivo de pruebas (`test_automatizado.py` en Backend, `test_automatizado.js` en Frontend) que cubren la lógica pura de cada lado — sin necesitar MQTT, InfluxDB, ni un navegador real corriendo. El detalle de qué cubre cada uno y cómo correrlas está en la sección "Pruebas automatizadas" de cada README (`Backend/README.md` y `Frontend/README.md`).

## Por dónde empezar a leer

1. Este archivo (`software/README.md`) — el mapa general.
2. `Backend/README.md` o `Frontend/README.md`, según qué lado te toque tocar.
3. `Backend/backend_core/README.md`, `Frontend/css/README.md` o `Frontend/js/README.md` — el detalle archivo por archivo, solo cuando necesites bajar a ese nivel.
