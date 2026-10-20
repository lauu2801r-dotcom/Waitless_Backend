from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import admin_o_empleado, es_personal, get_current_user
from app.modules.pedidos import service
from app.modules.pedidos.schemas import (
    PedidoActualizar,
    PedidoCrear,
    PedidoEditarItems,
    PedidoRespuesta,
)

router = APIRouter()


@router.post("/", response_model=PedidoRespuesta)
def crear_pedido(
    datos: PedidoCrear,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return service.crear_pedido(db, datos, int(current_user["sub"]))


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
    db: Session = Depends(get_db),
    current_user: dict = Depends(admin_o_empleado),
):
    return service.actualizar_estado_pedido(db, pedido_id, datos)


@router.put("/{pedido_id}/items", response_model=PedidoRespuesta)
def editar_items(
    pedido_id: int,
    datos: PedidoEditarItems,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return service.editar_items_pedido(
        db, pedido_id, int(current_user["sub"]), datos
    )


@router.delete("/{pedido_id}")
def cancelar_pedido(
    pedido_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return service.cancelar_pedido(db, pedido_id, int(current_user["sub"]))
