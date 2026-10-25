from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import admin_o_empleado, get_current_user, restaurante_id_de, solo_admin
from app.modules.auditoria import service as auditoria
from app.websocket.manager import manager
from app.modules.mesas import service
from app.modules.mesas.models import EstadoMesa
from app.modules.mesas.schemas import MesaActualizar, MesaCrear, MesaRespuesta

router = APIRouter()


@router.post("/", response_model=MesaRespuesta)
def crear_mesa(
    datos: MesaCrear,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    rid = restaurante_id_de(db, current_user)
    if rid is None:
        raise HTTPException(400, "Tu cuenta no tiene un restaurante asociado")
    mesa = service.crear_mesa(db, datos, rid)
    manager.emitir("mesas", {"tipo": "mesas_actualizadas", "mesa_id": mesa.id, "mensaje": f"Mesa {mesa.numero} creada"})
    auditoria.registrar(
        db, "mesa_creada", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="mesa", entidad_id=mesa.id,
        ip=auditoria.ip_de(request),
    )
    return mesa


@router.get("/", response_model=List[MesaRespuesta])
def listar_mesas(
    restaurante_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # Un administrador solo ve las mesas de su restaurante
    propio = restaurante_id_de(db, current_user)
    return service.obtener_mesas(db, restaurante_id=propio or restaurante_id)


@router.get("/disponibles", response_model=List[MesaRespuesta])
def mesas_disponibles(
    restaurante_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return service.obtener_mesas_disponibles(db, restaurante_id)


@router.get("/{mesa_id}", response_model=MesaRespuesta)
def obtener_mesa(
    mesa_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return service.obtener_mesa(db, mesa_id)


@router.patch("/{mesa_id}", response_model=MesaRespuesta)
def actualizar_mesa(
    mesa_id: int,
    datos: MesaActualizar,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    mesa = service.actualizar_mesa(db, mesa_id, datos)
    manager.emitir("mesas", {"tipo": "mesas_actualizadas", "mesa_id": mesa_id, "mensaje": f"Mesa {mesa.numero} modificada"})
    auditoria.registrar(
        db, "mesa_modificada", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="mesa", entidad_id=mesa_id,
        ip=auditoria.ip_de(request),
    )
    return mesa


@router.patch("/{mesa_id}/estado", response_model=MesaRespuesta)
def cambiar_estado(
    mesa_id: int,
    estado: EstadoMesa,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(admin_o_empleado),
):
    mesa = service.actualizar_estado_mesa(db, mesa_id, estado)
    evento = {"tipo": "estado_mesa", "mesa_id": mesa_id, "numero": mesa.numero,
              "estado": estado.value, "mensaje": f"Mesa {mesa.numero} cambió a {estado.value}"}
    manager.emitir("mesas", evento)
    manager.emitir("dashboard", evento)
    auditoria.registrar(
        db, "mesa_estado_cambiado", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="mesa", entidad_id=mesa_id,
        detalle=f"nuevo estado: {estado.value}", ip=auditoria.ip_de(request),
    )
    return mesa


@router.delete("/{mesa_id}")
def eliminar_mesa(
    mesa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    resultado = service.eliminar_mesa(db, mesa_id)
    manager.emitir("mesas", {"tipo": "mesas_actualizadas", "mesa_id": mesa_id, "mensaje": "Mesa eliminada"})
    auditoria.registrar(
        db, "mesa_eliminada", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="mesa", entidad_id=mesa_id,
        ip=auditoria.ip_de(request),
    )
    return resultado
