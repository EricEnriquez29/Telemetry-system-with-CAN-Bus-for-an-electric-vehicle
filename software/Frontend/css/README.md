# Hojas de estilo — Dashboard de Telemetría Fénix

**Escudería Fénix — UPIITA-IPN**
Ingeniería en Sistemas Automotrices

Carpeta: `software/Frontend/css/`

## Descripción

Esta carpeta contiene las 4 hojas de estilo CSS que definen la apariencia completa del dashboard. Están divididas por zona de la interfaz (no por componente ni por tipo de regla), y todas comparten el mismo sistema de variables de tema definido en `base.css`. `index.html` las importa en este orden:

```html
<link rel="stylesheet" href="css/base.css">
<link rel="stylesheet" href="css/sidebar.css">
<link rel="stylesheet" href="css/center.css">
<link rel="stylesheet" href="css/map-laps-historical.css">
```

El orden importa poco en la práctica (no hay reglas que se pisen entre archivos), pero se mantiene así porque `base.css` define las variables (`--orange`, `--bg`, etc.) que los otros 3 archivos consumen.

## Archivos

**`base.css`** — se encarga de las variables de tema y el "esqueleto" de la página, mediante `:root{...}` (colores, paneles, bordes) y reglas globales.
- Reset básico (`*{margin:0;...}`).
- Clases utilitarias de color (`.txt-orange`, `.txt-green`, `.txt-yellow`, `.txt-red`, `.txt-cyan`, `.txt-blue`, `.txt-text`) — así el HTML nunca necesita `style="color:..."` inline.
- Barra de título, subheader de estado (indicador WS/MGT), menú lateral (drawer + overlay), barra de luces de revoluciones.
- Layout general en grid de 3 columnas (`.body`) y estilos base de la tabla de vueltas.

**`sidebar.css`** — se encarga de las dos columnas laterales, mediante clases compartidas: secciones (`.sec`), subsecciones, y filas clave-valor (`.row`, `.rl-key`, `.rl-val`).

**`center.css`** — se encarga de la columna central, mediante estilos para: gauges (velocímetros Plotly), pedales (acelerador/freno), odómetro, indicador de batería (SOC), contactor, termómetros, y el bloque de las 4 gráficas en tiempo real (Chart.js).

**`map-laps-historical.css`** — se encarga de todo lo relacionado a GPS y vueltas, mediante:
- El mapa (Leaflet) y su overlay de zoom.
- El formulario de línea de meta.
- El resumen y tabla de celdas de batería (voltaje/resistencia).
- El modal de sesiones históricas (`.hist-*`) y la tabla de vueltas (`.lap-row`, `.lap-cell`).

## Convenciones

- **Variables CSS, no HEX repetidos.** Los colores viven como variables en `:root` (`base.css`) y se consumen con `var(--nombre)` en todo el resto del código. Evita agregar un color HEX suelto en un archivo nuevo; si necesitas un color, agrégalo como variable en `base.css`.
- **Nombres de clase en kebab-case**, cortos y con prefijo que indica la zona/componente (`gm-` para g-meter, `tb-` para pedales throttle/brake, `hist-` para el modal histórico, `lap-`/`ls-` para vueltas).
- **Sin frameworks de CSS** (no Tailwind, no Bootstrap): es CSS plano, escrito a mano, pensado para un layout fijo tipo "panel de instrumentos" más que para un sitio responsive tradicional.
- Antes existía un `base.css` duplicado en la raíz de `Frontend/` (no en `css/`) que no estaba enlazado por `index.html` y tenía valores de variables distintos a este. Fue eliminado — **esta carpeta `css/` es la única fuente de verdad para estilos**.

## Cómo modificar un color del tema

Cambia el valor de la variable correspondiente en `css/base.css` (por ejemplo `--orange:#EF5E20`); el cambio se propaga automáticamente a los otros 3 archivos CSS y a todos los elementos del HTML que usan la clase `.txt-orange` — **un solo lugar, un solo cambio**. Ya no hay `style="color:var(--x)"` repetido en `index.html`; si necesitas un color nuevo que no existe, agrega la variable en `:root` y su clase `.txt-nombre{color:var(--nombre);}` aquí mismo, junto a las demás.
