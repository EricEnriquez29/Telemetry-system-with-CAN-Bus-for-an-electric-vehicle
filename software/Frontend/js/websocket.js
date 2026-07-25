// ── Conexión WebSocket al backend ──
// La URL viene de FenixConfig (config.js) — antes estaba hardcodeada aquí
// y duplicada en historical-modal.js. connect() la llama main.js al cargar;
// setMgtConn la llama dashboard-render.js en cada mensaje.
(function () {
  var ws = null;
  var lastMsgTime = Date.now();

  function setConn(connected) {
    var dot = document.getElementById('ws-dot');
    var lbl = document.getElementById('ws-label');
    if (dot) { if (connected) dot.classList.add('connected'); else dot.classList.remove('connected'); }
    if (lbl) { lbl.textContent = connected ? 'Servidor conectado' : 'Servidor reconectando…'; }
  }

  function setMgtConn(connected) {
    var dot = document.getElementById('mgt-dot');
    var lbl = document.getElementById('mgt-label');
    if (!dot || !lbl) return;
    if (connected === null || connected === undefined) { lbl.textContent = 'MGT desconocido'; dot.classList.remove('connected'); }
    else if (connected) { dot.classList.add('connected'); lbl.textContent = 'MGT conectado'; }
    else { dot.classList.remove('connected'); lbl.textContent = 'MGT desconectado'; }
  }

  function connect() {
    try {
      if (ws) { ws.onopen = null; ws.onclose = null; ws.onerror = null; ws.onmessage = null; ws.close(); }
    } catch (e) { }
    ws = new WebSocket(FenixConfig.wsUrl);
    ws.onopen = () => { setConn(true); lastMsgTime = Date.now(); };
    ws.onmessage = (event) => {
      lastMsgTime = Date.now();
      try { updateDashboard(JSON.parse(event.data)); } catch (e) { console.error('Error en updateDashboard:', e); }
    };
    ws.onclose = () => { setConn(false); setTimeout(connect, 2000); };
    ws.onerror = () => { try { ws.close(); } catch (e) { } };
  }

  // ── Watchdog: si no llegan datos en 8s (socket colgado, onclose que no dispara,
  // pérdida de red sin aviso), forzar reconexión sin importar readyState ──
  setInterval(function () {
    if ((Date.now() - lastMsgTime) > 8000) {
      console.warn('WS sin datos por 8s, forzando reconexión');
      lastMsgTime = Date.now(); // evita disparos repetidos mientras reconecta
      connect();
    }
  }, 3000);

  window.connect = connect;
  window.setMgtConn = setMgtConn;
})();
