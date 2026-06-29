from fastapi import WebSocket
from typing import Dict, List
import json

class ConnectionManager:
    def __init__(self):
        # Conexiones activas por sala
        self.active_connections: Dict[str, List[WebSocket]] = {
            "mesas": [],
            "pedidos": [],
            "dashboard": []
        }

    async def connect(self, websocket: WebSocket, sala: str):
        await websocket.accept()
        if sala not in self.active_connections:
            self.active_connections[sala] = []
        self.active_connections[sala].append(websocket)

    def disconnect(self, websocket: WebSocket, sala: str):
        if sala in self.active_connections:
            if websocket in self.active_connections[sala]:
                self.active_connections[sala].remove(websocket)

    async def broadcast(self, sala: str, mensaje: dict):
        if sala in self.active_connections:
            conexiones_activas = self.active_connections[sala].copy()
            for connection in conexiones_activas:
                try:
                    await connection.send_text(json.dumps(mensaje))
                except Exception:
                    self.active_connections[sala].remove(connection)

    async def send_personal(self, websocket: WebSocket, mensaje: dict):
        try:
            await websocket.send_text(json.dumps(mensaje))
        except Exception:
            pass

    def get_active_connections_count(self, sala: str) -> int:
        return len(self.active_connections.get(sala, []))

manager = ConnectionManager()