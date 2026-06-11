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
import threading
from typing import Any, Dict, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Fénix Telemetry API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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