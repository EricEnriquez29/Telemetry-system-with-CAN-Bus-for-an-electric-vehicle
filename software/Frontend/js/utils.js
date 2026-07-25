// ── Utilidades compartidas ──
// Antes num()/fmtMP() vivían dentro de dashboard-render.js y historical-modal.js
// los usaba sin declarar la dependencia (funcionaba solo por orden de carga
// implícito). Aquí quedan centralizadas y explícitas para ambos archivos.

function num(v) {
  return (v === null || v === undefined || isNaN(v)) ? 0 : parseFloat(v);
}

function fmtMaxProm(valorMax, valorProm, decimales, ceroSiNulo) {
  decimales = decimales != null ? decimales : 0;
  var textoVacio = ceroSiNulo ? (0).toFixed(decimales) : '—';
  var maxTexto  = (valorMax  != null) ? valorMax.toFixed(decimales)  : textoVacio;
  var promTexto = (valorProm != null) ? valorProm.toFixed(decimales) : textoVacio;
  return maxTexto + '/' + promTexto;
}

function fmtDuracionMinSeg(segundos) {
  segundos = Math.round(segundos || 0);
  var min = Math.floor(segundos / 60), rest = segundos % 60;
  return min + ':' + String(rest).padStart(2, '0');
}

function fmtDecimalOGuion(valor, decimales) {
  return (valor == null) ? '—' : valor.toFixed(decimales != null ? decimales : 1);
}

function fmtDecimalOCero(valor, decimales) {
  return (valor == null ? 0 : valor).toFixed(decimales != null ? decimales : 1);
}

// Evita XSS si algún día session_id/date/etc. dejan de ser 100% confiables
// (por ejemplo si se vuelven editables por el usuario en el futuro).
function escapeHtml(valor) {
  return String(valor)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ── Fila de tabla de vueltas — usada tanto por la vista en vivo
// (dashboard-render.js) como por el modal de históricos (historical-modal.js).
// Antes cada archivo tenía su propia copia manual de este HTML: si se
// agregaba una columna en uno, era fácil olvidar el otro.
function buildLapRowHtml(vuelta, opciones) {
  opciones = opciones || {};
  var extraClass = opciones.extraClass ? ' ' + opciones.extraClass : '';
  var sinEstado = opciones.sinEstado ? ' no-estado' : '';
  var deltaTexto = (vuelta.delta_mejor == null) ? '—'
    : (vuelta.delta_mejor === 0 ? '—' : '+' + vuelta.delta_mejor.toFixed(1) + 's');
  var eConsumida = (vuelta.E_vuelta != null) ? vuelta.E_vuelta.toFixed(2) : '—';
  var eRegenerada = (vuelta.E_regen_vuelta != null) ? vuelta.E_regen_vuelta.toFixed(2) : '—';
  var eficiencia = (vuelta.eta_vuelta != null) ? vuelta.eta_vuelta.toFixed(1) : '—';

  var estadoCell = opciones.sinEstado ? '' :
    '<div class="lap-cell">' + escapeHtml(vuelta.estado || '') + '</div>';

  return (
    '<div class="lap-row' + extraClass + sinEstado + '">' +
    '<div class="lap-cell">' + escapeHtml(vuelta.n_lap) + '</div>' +
    '<div class="lap-cell">' + escapeHtml(vuelta.t_vuelta) + '<span class="lc-unit"> s</span></div>' +
    '<div class="lap-cell">' + deltaTexto + '</div>' +
    '<div class="lap-cell">' + escapeHtml(vuelta.d_vuelta) + '<span class="lc-unit"> km</span></div>' +
    '<div class="lap-cell">' + eConsumida + '<span class="lc-unit"> Wh</span></div>' +
    '<div class="lap-cell">' + eRegenerada + '<span class="lc-unit"> Wh</span></div>' +
    '<div class="lap-cell">' + eficiencia + '<span class="lc-unit"> Wh/km</span></div>' +
    '<div class="lap-cell">' + fmtMaxProm(vuelta.vel_max, vuelta.vel_prom, 1) + '<span class="lc-unit"> km/h</span></div>' +
    '<div class="lap-cell">' + fmtMaxProm(vuelta.p_hv_max, vuelta.p_hv_prom) + '<span class="lc-unit"> W</span></div>' +
    '<div class="lap-cell">' + fmtMaxProm(vuelta.p_regen_max, vuelta.p_regen_prom, 0, true) + '<span class="lc-unit"> W</span></div>' +
    '<div class="lap-cell">' + fmtMaxProm(vuelta.p_mec_max, vuelta.p_mec_prom) + '<span class="lc-unit"> W</span></div>' +
    '<div class="lap-cell">' + ((vuelta.Gx_max != null) ? vuelta.Gx_max.toFixed(2) : '—') + '</div>' +
    '<div class="lap-cell">' + ((vuelta.Gy_max != null) ? vuelta.Gy_max.toFixed(2) : '—') + '</div>' +
    '<div class="lap-cell">' + fmtMaxProm(vuelta.rpm_max, vuelta.rpm_prom) + '</div>' +
    estadoCell +
    '</div>'
  );
}

// Exporta estas funciones como módulo CommonJS SOLO cuando corren en Node
// (por ejemplo desde test_automatizado.js). En el navegador `module` no
// existe, así que esta rama nunca se ejecuta ahí — el comportamiento del
// dashboard no cambia en nada.
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    num, fmtMaxProm, fmtDuracionMinSeg, fmtDecimalOGuion, fmtDecimalOCero,
    escapeHtml, buildLapRowHtml
  };
}
