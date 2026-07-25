"""
meta_server.py — Servidor HTTP interno (puerto META_HTTP_PORT, default 8060)
que atiende las 3 rutas que consume el Frontend:

  POST /set_meta            setea la línea de meta (requiere header X-Meta-Token)
  GET  /sessions_for_date    lista de sesiones con datos en una fecha
  GET  /session_summary      resumen completo de una sesión histórica

Es el "controller" de esta capa: valida y autentica la entrada, y delega el
trabajo real a vueltas.py e historicos.py — no contiene lógica de negocio
ni construye consultas a InfluxDB directamente.
"""

import json
import logging
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from backend_core import config, historicos, vueltas

logger = logging.getLogger(__name__)

# Session id y fecha solo deben contener estos caracteres — cualquier otra
# cosa se rechaza con 400 antes de llegar a construir una consulta Flux con
# ese valor (ver nota de seguridad en historicos.build_session_summary).
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class _MetaHandler(BaseHTTPRequestHandler):

    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Meta-Token")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, {})

    def do_POST(self):
        if self.path != "/set_meta":
            self._send(404, {"error": "not_found"})
            return

        # ── Auth: el token se valida aquí, nunca en el cliente ──────────────
        token_recibido = self.headers.get("X-Meta-Token", "")
        if token_recibido != config.META_ACCESS_TOKEN:
            self._send(401, {"error": "token_invalido"})
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            lat_a = float(body["lat_a"]); lon_a = float(body["lon_a"])
            lat_b = float(body["lat_b"]); lon_b = float(body["lon_b"])
        except Exception:
            self._send(400, {"error": "json_invalido"})
            return

        if not (-90 <= lat_a <= 90 and -90 <= lat_b <= 90):
            self._send(400, {"error": "latitud_fuera_de_rango"}); return
        if not (-180 <= lon_a <= 180 and -180 <= lon_b <= 180):
            self._send(400, {"error": "longitud_fuera_de_rango"}); return
        if lat_a == lat_b and lon_a == lon_b:
            self._send(400, {"error": "PA_igual_a_PB"}); return

        vueltas.set_meta(lat_a, lon_a, lat_b, lon_b)
        self._send(200, {"status": "ok", "lat_a": lat_a, "lon_a": lon_a, "lat_b": lat_b, "lon_b": lon_b})

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/sessions_for_date":
            date_str = qs.get("date", [None])[0]
            if not date_str or not _DATE_RE.match(date_str):
                self._send(400, {"error": "falta_date_o_formato_invalido"})
                return
            try:
                sesiones = historicos.get_sessions_for_date(date_str)
            except Exception as e:
                self._send(500, {"error": str(e)})
                return
            self._send(200, {"date": date_str, "sessions": sesiones})
            return

        if parsed.path != "/session_summary":
            self._send(404, {"error": "not_found"})
            return
        date_str = qs.get("date", [None])[0]
        session_id = qs.get("session_id", [None])[0]
        if not date_str or not session_id:
            self._send(400, {"error": "faltan_parametros_date_session_id"})
            return
        if not _DATE_RE.match(date_str) or not _SESSION_ID_RE.match(session_id):
            self._send(400, {"error": "formato_invalido"})
            return
        try:
            summary = historicos.build_session_summary(date_str, session_id)
        except Exception as e:
            self._send(500, {"error": str(e)})
            return
        self._send(200, summary)

    def log_message(self, fmt, *args):
        pass  # silenciar el log por request de http.server


def start_meta_server():
    server = ThreadingHTTPServer(("0.0.0.0", config.META_HTTP_PORT), _MetaHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    logger.info(f"[META] Servidor HTTP /set_meta escuchando en puerto {config.META_HTTP_PORT}")
