from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.websocket.manager import manager

router = APIRouter()

@router.websocket("/mesas")
async def websocket_mesas(websocket: WebSocket):
    await manager.connect(websocket, "mesas")
    try:
        await manager.send_personal(websocket, {
            "tipo": "conexion",
            "mensaje": "Conectado al canal de mesas",
            "sala": "mesas"
        })
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, "mesas")

@router.websocket("/pedidos")
async def websocket_pedidos(websocket: WebSocket):
    await manager.connect(websocket, "pedidos")
    try:
        await manager.send_personal(websocket, {
            "tipo": "conexion",
            "mensaje": "Conectado al canal de pedidos",
            "sala": "pedidos"
        })
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, "pedidos")

@router.websocket("/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    await manager.connect(websocket, "dashboard")
    try:
        await manager.send_personal(websocket, {
            "tipo": "conexion",
            "mensaje": "Conectado al dashboard en tiempo real",
            "sala": "dashboard"
        })
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, "dashboard")