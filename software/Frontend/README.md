# Dashboard de Telemetría — Escudería Fénix

**Escudería Fénix — UPIITA-IPN**
Ingeniería en Sistemas Automotrices
Sistema de Telemetría con CAN Bus para Vehículo Eléctrico

Carpeta: `software/Frontend/`

## Descripción

Este es el **dashboard web** que muestra en tiempo real la telemetría del vehículo eléctrico de Escudería Fénix: velocidad, RPM, potencia, temperaturas, estado de las baterías (HV y auxiliar), posición GPS, dinámica vehicular (G's, roll/pitch) y conteo de vueltas en pista. También permite consultar el historial de sesiones anteriores y configurar la línea de meta para el conteo de vueltas.

Es una aplicación **web estática** (HTML + CSS + JavaScript vanilla, sin build step ni framework) que se conecta a un backend externo por WebSocket para recibir datos en tiempo real, y por HTTP para consultar históricos y setear la línea de meta.

## Características

- Gauges en tiempo real (velocidad, RPM, corriente) con Plotly.
- 4 gráficas de líneas con ventana deslizante de 15s (Chart.js).
- Mapa GPS en vivo con la posición del vehículo y la línea de meta (Leaflet).
- Objeto 3D del vehículo que rota según roll/pitch medidos por IMU (Three.js).
- Widgets dibujados a mano en Canvas 2D: batería, odómetro, contactor, G-meter, sag voltaje-corriente.
- Tabla de vueltas en vivo con estimaciones de autonomía y vuelta óptima.
- Modal de consulta de sesiones históricas (contra InfluxDB, vía el backend).
- Reconexión automática de WebSocket con watchdog ante pérdida de datos.
- Panel de 32 celdas de batería (16 de voltaje + 16 de resistencia interna).

## Tecnologías utilizadas

| Tecnología | Uso | Origen |
|---|---|---|
| HTML5 / CSS3 | Estructura y estilos | Propio |
| JavaScript ES6+ (vanilla) | Toda la lógica del dashboard, sin framework | Propio |
| [Chart.js 4.4.0](https://www.chartjs.org/) | Gráficas de líneas en tiempo real | CDN (jsDelivr) |
| [Plotly.js 2.27.0](https://plotly.com/javascript/) | Gauges tipo velocímetro | CDN (jsDelivr) |
| [Leaflet 1.9.4](https://leafletjs.com/) | Mapa GPS | CDN (jsDelivr) |
| [Three.js 0.160.0](https://threejs.org/) | Modelo 3D del vehículo | CDN (cdnjs) |
| Google Fonts (Share Tech Mono, Orbitron) | Tipografías del dashboard | CDN (Google) |
| WebSocket API | Telemetría en tiempo real | Nativo del navegador |
| Fetch API | Consultas HTTP (históricos, línea de meta) | Nativo del navegador |

No hay `package.json`, `npm install` ni bundler: todas las librerías externas se cargan directo desde CDN con hash de integridad (SRI).

## Estructura de la carpeta

```
software/Frontend/
├── index.html              Página única del dashboard (SPA de una sola vista con pestañas)
├── fenixpcarga.png          Logo mostrado en la pantalla de carga inicial
├── logofenix.png            Logo usado como favicon
├── css/                     Hojas de estilo (ver css/README.md)
│   ├── base.css
│   ├── sidebar.css
│   ├── center.css
│   └── map-laps-historical.css
└── js/                      Scripts (ver js/README.md)
    ├── config.js
    ├── utils.js
    ├── main.js
    ├── websocket.js
    ├── dashboard-render.js
    ├── menu.js
    ├── rev-lights.js
    ├── gauges.js
    ├── map.js
    ├── meta-form.js
    ├── historical-modal.js
    ├── thermo.js
    ├── cells-init.js
    ├── charts.js
    ├── canvas-widgets.js
    ├── horizon3d.js
    └── test_automatizado.js  Pruebas automatizadas — ver sección abajo
```

### `index.html`

**Se encarga de la estructura del dashboard**, mediante la pantalla de carga, el subheader de estado de conexión, el menú lateral, y las 3 pestañas (`tab-0` Principal, `tab-1` Tabla de Vueltas, `tab-2` Ploteo — sin implementar aún). Enlaza los 4 CSS y carga los 16 scripts al final del `<body>` en orden específico (ver `js/README.md`).

### `fenixpcarga.png` / `logofenix.png`

**Se encargan de los logos de Escudería Fénix**, mediante uno en la animación de carga inicial y otro como ícono de pestaña del navegador.

## Arquitectura

El Frontend sigue un patrón simple de **"un archivo por responsabilidad, todo orquestado por un solo punto de entrada de datos"**:

```
Backend (WebSocket) ──▶ websocket.js ──▶ dashboard-render.js ──▶ (actualiza cada widget)
                                                                     │
                              ┌──────────────────────────────────────┼──────────────────────────┐
                              ▼                ▼                ▼    ▼    ▼           ▼          ▼
                         gauges.js      canvas-widgets.js   thermo.js  map.js   charts.js   horizon3d.js
```

Cada mensaje de telemetría que llega por WebSocket pasa por `updateDashboard()` en `dashboard-render.js`, que es el único lugar que sabe leer el formato del payload y decide qué le pasa a cada widget. Los widgets (`gauges.js`, `canvas-widgets.js`, `thermo.js`, etc.) no saben nada del WebSocket ni del formato de los datos — solo exponen funciones puras de "dame estos valores, yo actualizo mi parte de la pantalla".

Cada archivo JS está aislado en su propio IIFE (ver `js/README.md` para el detalle de qué expone cada uno).

## Requisitos para usar el sistema

- Un navegador moderno con soporte de ES6+, WebSocket, Canvas 2D y WebGL (para el modelo 3D). Se probó sobre Chromium.
- Conexión de red hacia el backend (ver sección siguiente) — **no funciona completamente offline**: sin backend, el dashboard carga pero queda mostrando valores en cero/guion y el indicador de conexión en rojo.
- No requiere instalar nada: basta con abrir `index.html` en el navegador o servirlo con cualquier servidor HTTP estático (por ejemplo `python -m http.server` dentro de esta carpeta).

## Backend requerido

El dashboard consume dos servicios del backend (carpeta `software/Backend/`), cuyas URLs están centralizadas en `js/config.js` (`FenixConfig`):

| Servicio | Protocolo | Puerto (default) | Definido en `config.js` | Implementado en |
|---|---|---|---|---|
| Telemetría en tiempo real | WebSocket | 8050 | `FenixConfig.wsUrl` → `ws://<host>:8050/ws` | `fenix_api.py` (`@app.websocket("/ws")`) |
| Resumen de sesión histórica | HTTP GET | 8060 | `FenixConfig.sessionSummaryUrl` → `.../session_summary` | `fenix_backend.py` (`_MetaHandler.do_GET`, ruta `/session_summary?date=&session_id=`) |
| Lista de sesiones por fecha | HTTP GET | 8060 | `FenixConfig.sessionsForDateUrl` → `.../sessions_for_date` | `fenix_backend.py` (ruta `/sessions_for_date?date=`) |
| Setear línea de meta | HTTP POST | 8060 | `FenixConfig.setMetaUrl` → `.../set_meta` | `fenix_backend.py` (ruta `/set_meta`, requiere header `X-Meta-Token`) |

### Formato del mensaje WebSocket

Cada mensaje que llega por `/ws` es un JSON con esta forma (lo consume `updateDashboard(payload)` en `dashboard-render.js`):

```json
{
  "timestamp": "2026-07-12 09:32:44.137",
  "vehicle_id": "25",
  "session_id": "2026-07-12_0",
  "data": {
    "speed_v": 0, "rpm": 0, "throttle": 0, "brake": 0,
    "curr_p": 0, "volt_p": 0, "soc": 0,
    "cells": { "cell_1": 3.5, "...": "..." },
    "laps": [ { "n_lap": 1, "t_vuelta": 80.1, "...": "..." } ],
    "armado": true, "mgt_conectado": true
  }
}
```

El objeto `data` trae más de 60 campos (potencia, energía acumulada, salud de batería, GPS, orientación IMU, etc.) — la lista completa de campos que el Frontend sabe leer está en `updateDashboard()` (`js/dashboard-render.js`).

### Autenticación de la línea de meta

Para setear la línea de meta (`POST /set_meta`), el formulario (`meta-form.js`) envía el código de acceso en el header `X-Meta-Token`. La validación ocurre **del lado del backend** (`fenix_backend.py`, variable `META_ACCESS_TOKEN`, configurable por la variable de entorno `FENIX_META_TOKEN`) — el Frontend nunca compara ni almacena el token localmente.

### Cambiar de servidor backend

Para apuntar el dashboard a otro backend (por ejemplo un entorno de pruebas local), edita `js/config.js`:

```js
var FenixConfig = {
  BACKEND_HOST: "23.94.237.163",  // ← cambiar aquí
  WS_PORT: 8050,
  HTTP_PORT: 8060,
  ...
};
```

## Pruebas automatizadas

`js/test_automatizado.js` cubre las funciones puras de `utils.js` (formato de números, escape HTML, construcción de fila de la tabla de vueltas). Usa el test runner integrado de Node (`node:test`) — **no agrega ninguna dependencia nueva**, no hay `npm install` que hacer.

**No cubre** nada que dependa del DOM real, Canvas, WebGL o WebSocket (`dashboard-render.js`, `canvas-widgets.js`, `horizon3d.js`, etc.) — esas partes se siguen verificando a mano en el navegador.

```bash
cd software/Frontend
node --test js/test_automatizado.js
```

Igual que en el Backend, correr esto antes de subir un cambio detecta errores de lógica (por ejemplo en el formato de una columna de la tabla de vueltas) en segundos, sin tener que abrir el navegador.

## Convenciones

- **Idioma:** nombres de variables/funciones en español; nombres de propiedades del payload de telemetría en inglés/abreviado (vienen definidos por el backend/firmware, no se traducen).
- **IDs de HTML descriptivos:** cada `id` describe qué muestra (`motor-eficiencia`, `temp-motor-valor`, `celda-volt-3`), no una abreviatura críptica.
- **Colores centralizados, no inline:** los valores de color viven en 2 lugares nada más: las variables `:root` en `css/base.css` (la paleta) y las clases utilitarias `.txt-orange`/`.txt-green`/etc. (también en `base.css`). El HTML usa `class="rl-val txt-orange"`, nunca `style="color:..."` — cambiar un color del tema es una sola edición, no una búsqueda por 30 líneas.
- **Sin frameworks**: JS vanilla y CSS plano a propósito, para mantener el proyecto simple de mantener por el equipo sin depender de un toolchain de build.
- **Seguridad:** las librerías de CDN se cargan con hash SRI (`integrity=`); no hay secretos hardcodeados en el código fuente del cliente (ver sección de autenticación arriba).
- Ver también `css/README.md` y `js/README.md` para las convenciones específicas de cada subcarpeta.
