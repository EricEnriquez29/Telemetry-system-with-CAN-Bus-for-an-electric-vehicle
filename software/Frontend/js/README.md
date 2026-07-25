# Scripts — Dashboard de Telemetría Fénix

**Escudería Fénix — UPIITA-IPN**
Ingeniería en Sistemas Automotrices

Carpeta: `software/Frontend/js/`

## Descripción

Esta carpeta contiene los 16 archivos JavaScript (vanilla, sin framework ni build step) que le dan funcionalidad al dashboard: conexión en tiempo real con el backend, renderizado de todos los widgets, y las interacciones del usuario (menú, formulario de línea de meta, consulta de históricos). Un archivo adicional, `test_automatizado.js`, contiene las pruebas automatizadas (ver sección al final).

Cada archivo está envuelto en un **IIFE** (`(function(){...})()`) para que sus variables internas no vivan en el scope global de `window`. Solo se exponen explícitamente (vía `window.nombreFuncion = ...`) las funciones que otro archivo realmente necesita llamar — el resto queda privado. Esto evita que dos archivos usen por accidente el mismo nombre de variable y se pisen entre sí.

`index.html` carga los 16 archivos con `<script>` clásicos (no ES modules), en un orden específico que sí importa: los archivos compartidos (`config.js`, `utils.js`) van primero, y `dashboard-render.js` va antes que `websocket.js` para que `updateDashboard` ya exista cuando llegue el primer mensaje.

## Archivos

### Compartidos (usados por varios otros archivos)

**`config.js`** — se encarga de las URLs del backend, mediante un único objeto `FenixConfig` (`.wsUrl`, `.sessionSummaryUrl`, `.sessionsForDateUrl`, `.setMetaUrl`). Antes esta info estaba duplicada en `websocket.js` y `historical-modal.js`. Expone: `window.FenixConfig`.

**`utils.js`** — se encarga de formato de datos compartido, mediante funciones puras (`num`, `fmtMaxProm`, `fmtDuracionMinSeg`, `fmtDecimalOGuion`, `fmtDecimalOCero`, `escapeHtml`) y `buildLapRowHtml`, que genera el HTML de una fila de vuelta — la usan tanto la vista en vivo como el modal de históricos, para que ambas tablas tengan siempre las mismas columnas. Expone: todo lo anterior (en el navegador vía `window`; también exportable como módulo CommonJS para que `test_automatizado.js` lo pruebe con Node, sin afectar el navegador).

### Arranque y conexión

**`main.js`** — se encarga de arrancar la app, mediante la animación de carga inicial (spinner en canvas, 750ms) y una llamada final a `connect()`. Es el punto de entrada; no expone nada.

**`websocket.js`** — se encarga de la conexión en tiempo real, mediante un WebSocket contra `FenixConfig.wsUrl` con reintento automático (cada 2s) y un watchdog que fuerza reconexión si no llegan datos en 8s. Cada mensaje se parsea y se pasa a `updateDashboard()`. Expone: `window.connect`, `window.setMgtConn`.

### Orquestador principal

**`dashboard-render.js`** — se encarga de actualizar *todo* el dashboard, mediante `updateDashboard(payload)`, llamada en cada mensaje de telemetría: gauges, tabla de vueltas, celdas, termómetros, mapa, gráficas. Envuelto en `try/catch` completo para que un campo faltante no deje el dashboard a medias sin avisar. Expone: `window.updateDashboard`.

### Widgets individuales (cada uno dibuja/actualiza una parte específica de la UI)

**`menu.js`** — se encarga del menú lateral, mediante abrir/cerrar el drawer y cambiar entre las 3 pestañas. Expone: `window.toggleMenu`, `window.closeMenu`, `window.switchTab`.

**`rev-lights.js`** — se encarga del reloj y las luces de revoluciones, mediante un `setInterval` (reloj) y `updateRev(pct)` (10 luces según % de RPM). Expone: `window.updateRev`.

**`gauges.js`** — se encarga de los 3 velocímetros (velocidad, RPM, corriente), mediante Plotly al cargar la página. `dashboard-render.js` los actualiza después directo con `Plotly.update`. Autocontenido, no expone nada.

**`map.js`** — se encarga del mapa GPS, mediante Leaflet: posiciona el marcador del vehículo, dibuja/actualiza la línea de meta, y maneja el botón "Centrar". Expone: `window.centerMap`, `window.updateMap`, `window.drawMetaLine`.

**`meta-form.js`** — se encarga del formulario de línea de meta, mediante validación de coordenadas y envío del token de acceso al backend por header `X-Meta-Token` (ya no se valida en el cliente). Expone: `window.setMetaLine`.

**`historical-modal.js`** — se encarga del modal de sesiones pasadas, mediante 3 pasos: listar sesiones por fecha, pedir el resumen a `/session_summary`, y renderizarlo (estadísticas, top 3, tabla de vueltas idéntica a la vista en vivo). Expone: `window.openHistModal`, `closeHistModal`, `fetchSessionsForDate`, `loadHistSession`, `backToHistPicker`.

**`thermo.js`** — se encarga de una barra de temperatura, mediante `setThermo(idBase, val, max)`: ajusta ancho y color según umbral, y actualiza `<idBase>-barra`/`<idBase>-valor`. Expone: `window.setThermo`.

**`cells-init.js`** — se encarga de generar las 32 celdas de batería al cargar, mediante creación dinámica de DOM: 16 de voltaje (`celda-volt-1`…`16`) y 16 de resistencia (`celda-res-1`…`16`). Corre una sola vez; no expone nada.

**`charts.js`** — se encarga de las 4 gráficas en tiempo real, mediante Chart.js con ventana deslizante de 15s (velocidad/RPM/throttle, torque/potencia, potencia/corriente, regen). Expone: `window.FenixCharts` (`.push`, `.velocidad`, `.torquePotencia`, `.potenciaCorriente`, `.regen`).

**`canvas-widgets.js`** — se encarga de 6 widgets dibujados a mano en Canvas 2D (sin librería): batería tipo barras, odómetro de 7 segmentos, ícono de contactor, G-meter, sag voltaje-corriente, y potencia mecánica vs RPM coloreada por eficiencia. Expone: `window.drawBattery`, `drawOdo`, `drawContactor`, `drawGMeter`, `drawSag`, `drawPMRPM`.

**`horizon3d.js`** — se encarga del modelo 3D del vehículo, mediante Three.js: modela un karting simplificado y lo rota en tiempo real según roll/pitch (IMU). Expone: `window.updateHorizon`.

### Pruebas

**`test_automatizado.js`** — se encarga de probar las funciones puras de `utils.js`, mediante el test runner integrado de Node (`node:test`, sin dependencias nuevas). Se corre con `node --test js/test_automatizado.js` desde `software/Frontend/`. Ver "Pruebas automatizadas" en `../README.md` para el detalle de qué cubre y qué no.

## Convenciones

- **Un IIFE por archivo**, exponiendo solo lo estrictamente necesario en `window`.
- **Nombres de función y variable en español**, descriptivos y sin abreviar salvo estándares del dominio (`rpm`, `soc`, `Gx`/`Gy`/`Gz`).
- **Sin dependencias entre sí salvo las documentadas arriba** (columna "Expone"). Si un archivo nuevo necesita algo de otro, debe llamarlo por su función expuesta en `window`, nunca asumiendo variables internas.
- **Sin build step**: es JavaScript ES6+ que corre directo en el navegador vía `<script src="...">`. No hay bundler, transpilador ni `npm install` en el Frontend.
