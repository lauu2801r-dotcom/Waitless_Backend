import asyncio
import json
from typing import Dict, List, Optional

from fastapi import WebSocket


class ConnectionManager:
    """
    Administra las conexiones WebSocket por sala.

    Salas fijas: "mesas", "pedidos", "dashboard".
    Salas por usuario: "usuario:<id>" (notificaciones personales del cliente).
    """

    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {
            "mesas": [],
            "pedidos": [],
            "dashboard": [],
        }
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ---- bucle de eventos (para poder emitir desde endpoints síncronos) ----
    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def emitir(self, sala: str, mensaje: dict):
        """
        Versión SEGURA PARA CÓDIGO SÍNCRONO de broadcast.
        Los endpoints `def` de FastAPI corren en un hilo aparte; esta función
        agenda el envío en el bucle principal. Nunca lanza error: si algo
        falla en el tiempo real, la operación REST no debe romperse.
        """
        try:
            if self._loop is None or not self.active_connections.get(sala):
                return
            asyncio.run_coroutine_threadsafe(self.broadcast(sala, mensaje), self._loop)
        except Exception:
            pass

    # ---- conexiones ----
    async def connect(self, websocket: WebSocket, sala: str):
        await websocket.accept()
        self.active_connections.setdefault(sala, []).append(websocket)

    def disconnect(self, websocket: WebSocket, sala: str):
        conexiones = self.active_connections.get(sala)
        if conexiones is None:
            return
        if websocket in conexiones:
            conexiones.remove(websocket)
        # las salas por usuario se limpian cuando quedan vacías
        if sala.startswith("usuario:") and not conexiones:
            self.active_connections.pop(sala, None)

    async def broadcast(self, sala: str, mensaje: dict):
        for connection in list(self.active_connections.get(sala, [])):
            try:
                await connection.send_text(json.dumps(mensaje, default=str))
            except Exception:
                self.disconnect(connection, sala)

    async def send_personal(self, websocket: WebSocket, mensaje: dict):
        try:
            await websocket.send_text(json.dumps(mensaje, default=str))
        except Exception:
            pass

    def get_active_connections_count(self, sala: str) -> int:
        return len(self.active_connections.get(sala, []))


manager = ConnectionManager()
