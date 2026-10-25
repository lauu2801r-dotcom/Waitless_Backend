"""
WebSockets de WaitLess (autenticados).

Conexión:  ws://HOST:8000/ws/<canal>?token=<JWT>

Canales:
  /ws/mesas          cualquier usuario autenticado (estado de mesas)
  /ws/pedidos        admin / empleado (todos los pedidos: cocina, caja)
  /ws/dashboard      admin / empleado (métricas en vivo)
  /ws/mis-eventos    cualquier usuario (eventos personales: su pedido, su reserva)

Si el token falta o es inválido, la conexión se rechaza.
"""
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.database import SessionLocal
from app.core.security import verify_token
from app.modules.auth.models import RolUsuario, Usuario
from app.websocket.manager import manager

router = APIRouter()


def _autenticar(token: Optional[str]) -> Optional[dict]:
    """Devuelve {'id', 'email', 'rol'} si el token es válido y el usuario
    existe, está verificado y activo; si no, None."""
    if not token:
        return None
    payload = verify_token(token)
    if not payload or "sub" not in payload:
        return None
    try:
        uid = int(payload["sub"])
    except (TypeError, ValueError):
        return None
    db = SessionLocal()
    try:
        u = db.query(Usuario).filter(Usuario.id == uid).first()
        if not u or not u.activo or not u.verificado:
            return None
        rol = getattr(u.rol, "value", u.rol)
        return {"id": u.id, "email": u.email, "rol": rol}
    finally:
        db.close()


def _es_personal(user: dict) -> bool:
    return user["rol"] in (RolUsuario.administrador.value, RolUsuario.empleado.value)


async def _atender(websocket: WebSocket, sala: str, token: Optional[str],
                   solo_personal: bool, saludo: str):
    user = _autenticar(token)
    if user is None or (solo_personal and not _es_personal(user)):
        # Se cierra antes de aceptar: el cliente recibe el rechazo del handshake.
        await websocket.close(code=4401)
        return
    await manager.connect(websocket, sala)
    try:
        await manager.send_personal(websocket, {
            "tipo": "conexion", "mensaje": saludo, "sala": sala,
        })
        while True:
            texto = await websocket.receive_text()
            if texto == "ping":
                await manager.send_personal(websocket, {"tipo": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, sala)


@router.websocket("/mesas")
async def websocket_mesas(websocket: WebSocket, token: Optional[str] = None):
    await _atender(websocket, "mesas", token, False, "Conectado al canal de mesas")


@router.websocket("/pedidos")
async def websocket_pedidos(websocket: WebSocket, token: Optional[str] = None):
    await _atender(websocket, "pedidos", token, True, "Conectado al canal de pedidos")


@router.websocket("/dashboard")
async def websocket_dashboard(websocket: WebSocket, token: Optional[str] = None):
    await _atender(websocket, "dashboard", token, True, "Conectado al dashboard en tiempo real")


@router.websocket("/mis-eventos")
async def websocket_mis_eventos(websocket: WebSocket, token: Optional[str] = None):
    user = _autenticar(token)
    if user is None:
        await websocket.close(code=4401)
        return
    await _atender(websocket, f"usuario:{user['id']}", token, False,
                   "Conectado a tus notificaciones")
