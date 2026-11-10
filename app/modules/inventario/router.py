from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import admin_o_empleado, restaurante_requerido, solo_admin
from app.modules.auditoria import service as auditoria
from app.modules.inventario import service
from app.modules.inventario.models import TipoMovimiento
from app.modules.inventario.schemas import (
    InsumoActualizar, InsumoCrear, InsumoRespuesta, MovimientoCrear,
    MovimientoRespuesta, ProveedorActualizar, ProveedorCrear,
    ProveedorRespuesta, ResumenInventario,
)
from app.websocket.manager import manager

router = APIRouter()


# ───────────────────────── Proveedores ─────────────────────────
@router.post("/proveedores", response_model=ProveedorRespuesta)
def crear_proveedor(
    datos: ProveedorCrear, request: Request,
    db: Session = Depends(get_db), current_user: dict = Depends(solo_admin),
):
    rid = restaurante_requerido(db, current_user)
    prov = service.crear_proveedor(db, datos, rid)
    auditoria.registrar(
        db, "proveedor_creado", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="proveedor", entidad_id=prov.id,
        detalle=prov.nombre, ip=auditoria.ip_de(request),
    )
    return prov


@router.get("/proveedores", response_model=List[ProveedorRespuesta])
def listar_proveedores(
    activo: Optional[bool] = True,
    db: Session = Depends(get_db), current_user: dict = Depends(admin_o_empleado),
):
    return service.listar_proveedores(db, restaurante_requerido(db, current_user), activo)


@router.patch("/proveedores/{proveedor_id}", response_model=ProveedorRespuesta)
def actualizar_proveedor(
    proveedor_id: int, datos: ProveedorActualizar, request: Request,
    db: Session = Depends(get_db), current_user: dict = Depends(solo_admin),
):
    prov = service.actualizar_proveedor(
        db, proveedor_id, datos, restaurante_requerido(db, current_user)
    )
    auditoria.registrar(
        db, "proveedor_modificado", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="proveedor", entidad_id=proveedor_id,
        ip=auditoria.ip_de(request),
    )
    return prov


# ───────────────────────── Insumos ─────────────────────────
@router.post("/insumos", response_model=InsumoRespuesta)
def crear_insumo(
    datos: InsumoCrear, request: Request,
    db: Session = Depends(get_db), current_user: dict = Depends(solo_admin),
):
    rid = restaurante_requerido(db, current_user)
    insumo = service.crear_insumo(db, datos, int(current_user["sub"]), current_user["email"], rid)
    auditoria.registrar(
        db, "insumo_creado", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="insumo", entidad_id=insumo.id,
        detalle=insumo.nombre, ip=auditoria.ip_de(request),
    )
    manager.emitir("dashboard", {"tipo": "inventario_actualizado", "insumo_id": insumo.id},
                   restaurante_id=rid)
    return insumo


@router.get("/insumos", response_model=List[InsumoRespuesta])
def listar_insumos(
    categoria: Optional[str] = None,
    buscar: Optional[str] = None,
    estado: Optional[str] = Query(None, pattern="^(ok|bajo|agotado)$"),
    activo: Optional[bool] = True,
    db: Session = Depends(get_db), current_user: dict = Depends(admin_o_empleado),
):
    rid = restaurante_requerido(db, current_user)
    return service.listar_insumos(db, rid, categoria, buscar, estado, activo)


@router.get("/resumen", response_model=ResumenInventario)
def resumen(db: Session = Depends(get_db), current_user: dict = Depends(admin_o_empleado)):
    return service.resumen(db, restaurante_requerido(db, current_user))


@router.get("/alertas", response_model=List[InsumoRespuesta])
def alertas(db: Session = Depends(get_db), current_user: dict = Depends(admin_o_empleado)):
    return service.alertas(db, restaurante_requerido(db, current_user))


@router.get("/insumos/{insumo_id}", response_model=InsumoRespuesta)
def obtener_insumo(
    insumo_id: int, db: Session = Depends(get_db),
    current_user: dict = Depends(admin_o_empleado),
):
    return service.obtener_insumo(db, insumo_id, restaurante_requerido(db, current_user))


@router.patch("/insumos/{insumo_id}", response_model=InsumoRespuesta)
def actualizar_insumo(
    insumo_id: int, datos: InsumoActualizar, request: Request,
    db: Session = Depends(get_db), current_user: dict = Depends(solo_admin),
):
    rid = restaurante_requerido(db, current_user)
    insumo = service.actualizar_insumo(db, insumo_id, datos, rid)
    auditoria.registrar(
        db, "insumo_modificado", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="insumo", entidad_id=insumo_id,
        ip=auditoria.ip_de(request),
    )
    manager.emitir("dashboard", {"tipo": "inventario_actualizado", "insumo_id": insumo_id},
                   restaurante_id=rid)
    return insumo


# ───────────────────────── Movimientos ─────────────────────────
@router.post("/movimientos", response_model=MovimientoRespuesta)
def registrar_movimiento(
    datos: MovimientoCrear, request: Request,
    db: Session = Depends(get_db), current_user: dict = Depends(admin_o_empleado),
):
    rid = restaurante_requerido(db, current_user)
    mov, insumo, hay_alerta = service.registrar_movimiento(
        db, datos, int(current_user["sub"]), current_user["email"], rid
    )
    auditoria.registrar(
        db, f"inventario_{mov.tipo.value}", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="insumo", entidad_id=insumo.id,
        detalle=f"{insumo.nombre}: {mov.cantidad} {insumo.unidad} ({mov.motivo or 'sin motivo'})",
        ip=auditoria.ip_de(request),
    )
    manager.emitir("dashboard", {
        "tipo": "inventario_actualizado", "insumo_id": insumo.id,
        "stock_actual": insumo.stock_actual, "estado": insumo.estado,
    }, restaurante_id=rid)
    if hay_alerta:
        manager.emitir("dashboard", {
            "tipo": "stock_bajo", "insumo_id": insumo.id, "nombre": insumo.nombre,
            "stock_actual": insumo.stock_actual, "stock_minimo": insumo.stock_minimo,
            "estado": insumo.estado,
            "mensaje": f"⚠️ {insumo.nombre}: quedan {insumo.stock_actual} {insumo.unidad} "
                       f"(mínimo {insumo.stock_minimo})",
        }, restaurante_id=rid)
    return mov


@router.get("/movimientos", response_model=List[MovimientoRespuesta])
def historial(
    insumo_id: Optional[int] = None,
    tipo: Optional[TipoMovimiento] = None,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), current_user: dict = Depends(admin_o_empleado),
):
    rid = restaurante_requerido(db, current_user)
    return service.listar_movimientos(db, rid, insumo_id, tipo, desde, hasta, limit, offset)
