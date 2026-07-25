// ── Configuración central del backend ──
// Única fuente de verdad para host/puertos: si el servidor cambia, solo se
// edita aquí (antes estaba repetido en websocket.js y historical-modal.js).
var FenixConfig = {
  BACKEND_HOST: "23.94.237.163",
  WS_PORT: 8050,
  HTTP_PORT: 8060,

  get wsUrl() {
    return "ws://" + this.BACKEND_HOST + ":" + this.WS_PORT + "/ws";
  },
  get sessionSummaryUrl() {
    return "http://" + this.BACKEND_HOST + ":" + this.HTTP_PORT + "/session_summary";
  },
  get sessionsForDateUrl() {
    return "http://" + this.BACKEND_HOST + ":" + this.HTTP_PORT + "/sessions_for_date";
  },
  get setMetaUrl() {
    return "http://" + this.BACKEND_HOST + ":" + this.HTTP_PORT + "/set_meta";
  }
};
