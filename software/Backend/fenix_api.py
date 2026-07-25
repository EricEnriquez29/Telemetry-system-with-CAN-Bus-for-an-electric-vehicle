"""
fenix_api.py  –  Escudería Fénix
- Recibe snapshots del backend via POST /internal/snapshot
- Los empuja por WebSocket a todos los clientes conectados (dashboard)
- También expone GET /api/latest para compatibilidad

Uso:
    pip install fastapi uvicorn websockets
    uvicorn fenix_api:app --host 0.0.0.0 --port 8050
"""

import asyncio
import json
import os
import threading
from typing import Any, Dict, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Fénix Telemetry API")

# ─── CORS ──────────────────────────────────────────────────────────────────
# Antes: allow_origins=["*"] fijo en el código, sin forma de restringirlo.
# Ahora: se lee de FENIX_ALLOWED_ORIGINS (lista separada por comas, p.ej.
# "https://dashboard.escuderiafenix.mx,http://192.168.1.50:8080"). Si no se
# define, sigue permitiendo cualquier origen — mismo comportamiento de
# antes — pero avisa en el arranque para que no quede así "por accidente".
#
# Nota: esto solo restringe qué páginas web (navegador) pueden leer las
# respuestas de esta API vía JS. No protege /internal/snapshot contra un
# cliente que no sea un navegador (curl, otro script) — eso requeriría
# autenticación real en ese endpoint, igual que se hizo con /set_meta en
# fenix_backend.py.
_origins_env = os.environ.get("FENIX_ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = [o.strip() for o in _origins_env.split(",") if o.strip()] or ["*"]

if ALLOWED_ORIGINS == ["*"]:
    print(
        "[WARN] CORS abierto a todos los orígenes (*). "
        "Define FENIX_ALLOWED_ORIGINS con el dominio real del dashboard antes de producción.",
        flush=True,
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ─── Estado global ────────────────────────────────────────────────────────────
_lock:             threading.Lock          = threading.Lock()
_latest_snapshot:  Optional[Dict[str, Any]] = None
_ws_clients:       Set[WebSocket]          = set()
_loop:             Optional[asyncio.AbstractEventLoop] = None

# ─── Modelo de entrada ────────────────────────────────────────────────────────
class Snapshot(BaseModel):
    timestamp:  str
    vehicle_id: str
    session_id: str
    data:       Dict[str, Any]

# ─── Guardar loop al arrancar ─────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    global _loop
    _loop = asyncio.get_event_loop()

# ─── Endpoint interno: fenix_backend empuja aquí ──────────────────────────────
@app.post("/internal/snapshot")
async def receive_snapshot(snapshot: Snapshot):
    global _latest_snapshot
    payload = snapshot.dict()

    with _lock:
        _latest_snapshot = payload

    # Emitir a todos los clientes WebSocket conectados
    if _ws_clients:
        message = json.dumps(payload)
        dead = set()
        for ws in list(_ws_clients):
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        _ws_clients.difference_update(dead)

    return {"status": "ok"}

# ─── Endpoint WebSocket: el dashboard se conecta aquí ────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.add(websocket)

    # Mandar el último snapshot inmediatamente al conectarse
    with _lock:
        last = _latest_snapshot
    if last:
        await websocket.send_text(json.dumps(last))

    try:
        while True:
            # Mantener conexión viva esperando mensajes del cliente
            await websocket.receive_text()
    except WebSocketDisconnect:
        _ws_clients.discard(websocket)

# ─── Endpoint REST: compatibilidad ───────────────────────────────────────────
@app.get("/api/latest")
def get_latest():
    with _lock:
        if _latest_snapshot is None:
            return {"status": "no_data", "data": {}}
        return {"status": "ok", **_latest_snapshot}