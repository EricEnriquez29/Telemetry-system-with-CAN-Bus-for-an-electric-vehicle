// ── Reloj del subheader + luces de revoluciones (shift lights) ──
// updateRev se expone porque dashboard-render.js la llama en cada mensaje.
(function () {
  setInterval(() => { document.getElementById('reloj').textContent = new Date().toLocaleTimeString('es-MX'); }, 1000);

  var luces = document.getElementById('revbar').children;
  var COLORES_LUCES = ['#3ba776', '#3ba776', '#3ba776', '#3ba776', '#3ba776', '#cc4055', '#cc4055', '#cc4055', '#cc4055', '#cc4055'];

  function updateRev(pct) {
    var n = Math.floor(pct * 10);
    for (var i = 0; i < 10; i++) {
      luces[i].style.background = i < n ? COLORES_LUCES[i] : '#111';
      luces[i].style.boxShadow = i < n ? '0 0 6px ' + COLORES_LUCES[i] : 'none';
    }
  }

  window.updateRev = updateRev;
})();
