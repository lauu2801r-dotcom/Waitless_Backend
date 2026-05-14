from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.core.security import verify_token
from app.modules.pedidos import service
from app.modules.pedidos.schemas import (
    PedidoCrear,
    PedidoActualizar,
    PedidoRespuesta,
    PedidoEditarItems,
)

router = APIRouter()

def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token requerido"
        )
    token = authorization.split(" ")[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado"
        )
    return payload

@router.post("/", response_model=PedidoRespuesta)
def crear_pedido(
    datos: PedidoCrear,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return service.crear_pedido(db, datos, int(current_user["sub"]))

@router.get("/mis-pedidos", response_model=List[PedidoRespuesta])
def mis_pedidos(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return service.obtener_pedidos_usuario(db, int(current_user["sub"]))

@router.get("/todos", response_model=List[PedidoRespuesta])
def todos_pedidos(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return service.obtener_todos_pedidos(db)

@router.get("/activos", response_model=List[PedidoRespuesta])
def pedidos_activos(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return service.obtener_pedidos_activos(db)

@router.get("/{pedido_id}", response_model=PedidoRespuesta)
def obtener_pedido(
    pedido_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return service.obtener_pedido(db, pedido_id)

@router.patch("/{pedido_id}", response_model=PedidoRespuesta)
def actualizar_pedido(
    pedido_id: int,
    datos: PedidoActualizar,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return service.actualizar_estado_pedido(db, pedido_id, datos)

@router.delete("/{pedido_id}")
def cancelar_pedido(
    pedido_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return service.cancelar_pedido(db, pedido_id, int(current_user["sub"]))

@router.put("/{pedido_id}/items", response_model=PedidoRespuesta)
def editar_items_pedido(
    pedido_id: int,
    datos: PedidoEditarItems,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return service.editar_items_pedido(db, pedido_id, int(current_user["sub"]), datos)