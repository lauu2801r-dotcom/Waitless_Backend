from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import admin_o_empleado, es_personal, get_current_user
from app.modules.auditoria import service as auditoria
from app.modules.pedidos import service
from app.websocket.manager import manager
from app.modules.pedidos.schemas import (
    PedidoActualizar,
    PedidoCrear,
    PedidoEditarItems,
    PedidoRespuesta,
)

router = APIRouter()


def _valor(x):
    """Devuelve el texto de un Enum (o el valor tal cual)."""
    return getattr(x, "value", x)


@router.post("/", response_model=PedidoRespuesta)
def crear_pedido(
    datos: PedidoCrear,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    pedido = service.crear_pedido(db, datos, int(current_user["sub"]))
    evento = {"tipo": "pedido_nuevo", "pedido_id": pedido.id,
              "mesa_id": pedido.mesa_id, "estado": _valor(pedido.estado),
              "mensaje": f"Nuevo pedido #{pedido.id}"}
    manager.emitir("pedidos", evento)
    manager.emitir("dashboard", evento)
    manager.emitir("mesas", {"tipo": "mesas_actualizadas", "mesa_id": pedido.mesa_id})
    auditoria.registrar(
        db, "pedido_creado", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="pedido", entidad_id=pedido.id,
        ip=auditoria.ip_de(request),
    )
    return pedido


@router.get("/mis-pedidos", response_model=List[PedidoRespuesta])
def mis_pedidos(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return service.obtener_pedidos_usuario(db, int(current_user["sub"]))


@router.get("/todos", response_model=List[PedidoRespuesta])
def todos_pedidos(
    db: Session = Depends(get_db),
    current_user: dict = Depends(admin_o_empleado),
):
    return service.obtener_todos_pedidos(db)


@router.get("/activos", response_model=List[PedidoRespuesta])
def pedidos_activos(
    db: Session = Depends(get_db),
    current_user: dict = Depends(admin_o_empleado),
):
    return service.obtener_pedidos_activos(db)


@router.get("/{pedido_id}", response_model=PedidoRespuesta)
def obtener_pedido(
    pedido_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    pedido = service.obtener_pedido(db, pedido_id)
    # Un cliente solo puede ver sus propios pedidos
    if not es_personal(current_user) and pedido.usuario_id != int(current_user["sub"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para ver este pedido",
        )
    return pedido


@router.patch("/{pedido_id}", response_model=PedidoRespuesta)
def actualizar_pedido(
    pedido_id: int,
    datos: PedidoActualizar,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(admin_o_empleado),
):
    pedido = service.actualizar_estado_pedido(db, pedido_id, datos)
    evento = {"tipo": "pedido_estado", "pedido_id": pedido_id,
              "mesa_id": pedido.mesa_id, "estado": _valor(pedido.estado),
              "mensaje": f"Pedido #{pedido_id}: {_valor(pedido.estado)}"}
    manager.emitir("pedidos", evento)
    manager.emitir("dashboard", evento)
    manager.emitir(f"usuario:{pedido.usuario_id}", evento)
    manager.emitir("mesas", {"tipo": "mesas_actualizadas", "mesa_id": pedido.mesa_id})
    auditoria.registrar(
        db, "pedido_estado_cambiado", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="pedido", entidad_id=pedido_id,
        detalle=f"nuevo estado: {_valor(pedido.estado)}",
        ip=auditoria.ip_de(request),
    )
    return pedido


@router.put("/{pedido_id}/items", response_model=PedidoRespuesta)
def editar_items(
    pedido_id: int,
    datos: PedidoEditarItems,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    pedido = service.editar_items_pedido(
        db, pedido_id, int(current_user["sub"]), datos
    )
    evento = {"tipo": "pedido_editado", "pedido_id": pedido_id,
              "mensaje": f"Pedido #{pedido_id} modificado"}
    manager.emitir("pedidos", evento)
    manager.emitir("dashboard", evento)
    auditoria.registrar(
        db, "pedido_items_editados", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="pedido", entidad_id=pedido_id,
        ip=auditoria.ip_de(request),
    )
    return pedido


@router.delete("/{pedido_id}")
def cancelar_pedido(
    pedido_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    resultado = service.cancelar_pedido(db, pedido_id, int(current_user["sub"]))
    evento = {"tipo": "pedido_cancelado", "pedido_id": pedido_id,
              "mensaje": f"Pedido #{pedido_id} cancelado"}
    manager.emitir("pedidos", evento)
    manager.emitir("dashboard", evento)
    manager.emitir("mesas", {"tipo": "mesas_actualizadas"})
    auditoria.registrar(
        db, "pedido_cancelado", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="pedido", entidad_id=pedido_id,
        ip=auditoria.ip_de(request),
    )
    return resultado
