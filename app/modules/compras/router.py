from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import admin_o_empleado, solo_admin
from app.modules.auditoria import service as auditoria
from app.modules.compras import service
from app.modules.compras.models import EstadoOrden
from app.modules.compras.schemas import (
    MetricasProveedor, OrdenActualizar, OrdenCrear, OrdenRespuesta,
    OrdenResumen, RecepcionCrear,
)
from app.websocket.manager import manager

router = APIRouter()


def _aviso(orden, mensaje: str):
    manager.emitir("dashboard", {
        "tipo": "orden_compra_actualizada", "orden_id": orden.id,
        "estado": orden.estado.value, "mensaje": mensaje,
    })


@router.post("/ordenes", response_model=OrdenRespuesta)
def crear_orden(
    datos: OrdenCrear, request: Request,
    db: Session = Depends(get_db), current_user: dict = Depends(solo_admin),
):
    orden = service.crear_orden(db, datos, int(current_user["sub"]), current_user["email"])
    auditoria.registrar(
        db, "orden_compra_creada", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="orden_compra", entidad_id=orden.id,
        detalle=f"{orden.proveedor_nombre}: ${orden.total}", ip=auditoria.ip_de(request),
    )
    _aviso(orden, f"Nueva orden de compra #{orden.id}")
    return orden


@router.get("/ordenes", response_model=List[OrdenResumen])
def listar_ordenes(
    estado: Optional[EstadoOrden] = None,
    proveedor_id: Optional[int] = None,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), current_user: dict = Depends(admin_o_empleado),
):
    return service.listar_ordenes(db, estado, proveedor_id, desde, hasta, limit, offset)


@router.get("/ordenes/{orden_id}", response_model=OrdenRespuesta)
def obtener_orden(
    orden_id: int, db: Session = Depends(get_db),
    current_user: dict = Depends(admin_o_empleado),
):
    return service.obtener_orden(db, orden_id)


@router.patch("/ordenes/{orden_id}", response_model=OrdenRespuesta)
def actualizar_orden(
    orden_id: int, datos: OrdenActualizar, request: Request,
    db: Session = Depends(get_db), current_user: dict = Depends(solo_admin),
):
    orden = service.actualizar_orden(
        db, orden_id, datos, int(current_user["sub"]), current_user["email"]
    )
    auditoria.registrar(
        db, "orden_compra_modificada", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="orden_compra", entidad_id=orden_id,
        ip=auditoria.ip_de(request),
    )
    _aviso(orden, f"Orden de compra #{orden_id} modificada")
    return orden


@router.post("/ordenes/{orden_id}/recibir", response_model=OrdenRespuesta)
def recibir_orden(
    orden_id: int, datos: RecepcionCrear, request: Request,
    db: Session = Depends(get_db), current_user: dict = Depends(admin_o_empleado),
):
    orden = service.recibir_orden(
        db, orden_id, datos, int(current_user["sub"]), current_user["email"]
    )
    auditoria.registrar(
        db, "orden_compra_recibida", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="orden_compra", entidad_id=orden_id,
        detalle=f"estado: {orden.estado.value}", ip=auditoria.ip_de(request),
    )
    _aviso(orden, f"Orden de compra #{orden_id}: {orden.estado.value}")
    manager.emitir("dashboard", {"tipo": "inventario_actualizado"})  # el stock subió
    return orden


@router.post("/ordenes/{orden_id}/cancelar", response_model=OrdenRespuesta)
def cancelar_orden(
    orden_id: int, request: Request,
    db: Session = Depends(get_db), current_user: dict = Depends(solo_admin),
):
    orden = service.cancelar_orden(db, orden_id, int(current_user["sub"]), current_user["email"])
    auditoria.registrar(
        db, "orden_compra_cancelada", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="orden_compra", entidad_id=orden_id,
        ip=auditoria.ip_de(request),
    )
    _aviso(orden, f"Orden de compra #{orden_id} cancelada")
    return orden


@router.get("/metricas", response_model=List[MetricasProveedor])
def metricas_todos(db: Session = Depends(get_db), current_user: dict = Depends(solo_admin)):
    return service.metricas_todos(db)


@router.get("/proveedores/{proveedor_id}/metricas", response_model=MetricasProveedor)
def metricas_proveedor(
    proveedor_id: int, db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    return service.metricas_proveedor(db, proveedor_id)
