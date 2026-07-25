// ── Barras de temperatura ──
// setThermo se expone porque dashboard-render.js la llama para cada sensor.
// Recibe la base del id (p.ej. "temp-motor") y actualiza "<base>-barra" y
// "<base>-valor".
(function () {
  function setThermo(idBase, val, max) {
    var pct = Math.min(100, val / max * 100);
    var col = val < max * 0.6 ? '#3ba776' : val < max * 0.8 ? '#c2a838' : '#cc4055';
    document.getElementById(idBase + '-barra').style.width = pct + '%';
    document.getElementById(idBase + '-barra').style.background = col;
    document.getElementById(idBase + '-valor').textContent = val.toFixed(0) + '°';
  }

  window.setThermo = setThermo;
})();
