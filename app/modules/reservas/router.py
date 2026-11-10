from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import admin_o_empleado, get_current_user, restaurante_id_de
from app.modules.auditoria import service as auditoria
from app.modules.notificaciones import service as notificaciones
from app.modules.reservas import service
from app.modules.reservas.schemas import ReservaActualizar, ReservaCrear, ReservaRespuesta
from app.websocket.manager import manager

router = APIRouter()


def _emitir(reserva, tipo: str, mensaje: str) -> None:
    """Avisa en vivo: al restaurante (dashboard/mesas) y al cliente dueño de la reserva."""
    manager.emitir("dashboard", {"tipo": tipo, "reserva_id": reserva.id,
                                 "mesa_id": reserva.mesa_id, "mensaje": mensaje})
    manager.emitir("mesas", {"tipo": "mesas_actualizadas", "mesa_id": reserva.mesa_id})
    manager.emitir(f"usuario:{reserva.usuario_id}", {
        "tipo": "reserva_estado", "reserva_id": reserva.id,
        "estado": reserva.estado.value if hasattr(reserva.estado, "value") else str(reserva.estado),
        "mensaje": mensaje,
    })


@router.post("/", response_model=ReservaRespuesta)
def crear_reserva(
    datos: ReservaCrear, request: Request,
    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user),
):
    uid = int(current_user["sub"])
    reserva = service.crear_reserva(db, datos, uid)
    _emitir(reserva, "reserva_nueva", f"Nueva reserva #{reserva.id}")
    notificaciones.avisar_reserva(db, reserva, "creada")
    notificaciones.avisar_reserva_al_restaurante(db, reserva, "creada", excluir_usuario_id=uid)
    auditoria.registrar(db, "reserva_creada", usuario_id=uid, email=current_user["email"],
                        entidad="reserva", entidad_id=reserva.id, ip=auditoria.ip_de(request))
    return reserva


@router.get("/mis-reservas", response_model=List[ReservaRespuesta])
def mis_reservas(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return service.obtener_reservas(db, int(current_user["sub"]))


@router.get("/todas", response_model=List[ReservaRespuesta])
def todas_reservas(db: Session = Depends(get_db), current_user: dict = Depends(admin_o_empleado)):
    return service.obtener_todas_reservas(db, restaurante_id_de(db, current_user))


@router.get("/{reserva_id}", response_model=ReservaRespuesta)
def obtener_reserva(reserva_id: int, db: Session = Depends(get_db),
                    current_user: dict = Depends(get_current_user)):
    reserva = service.obtener_reserva(db, reserva_id)
    if not service.puede_gestionar(db, reserva, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="No tienes permiso para ver esta reserva")
    return reserva


@router.patch("/{reserva_id}", response_model=ReservaRespuesta)
def actualizar_reserva(
    reserva_id: int, datos: ReservaActualizar, request: Request,
    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user),
):
    uid = int(current_user["sub"])
    reserva = service.actualizar_reserva(db, reserva_id, datos, current_user)
    _emitir(reserva, "reserva_modificada", f"Reserva #{reserva_id} modificada")
    notificaciones.avisar_reserva(db, reserva, "modificada")
    if reserva.usuario_id == uid:  # el cliente la cambió → avisar al restaurante
        notificaciones.avisar_reserva_al_restaurante(db, reserva, "modificada", excluir_usuario_id=uid)
    auditoria.registrar(db, "reserva_modificada", usuario_id=uid, email=current_user["email"],
                        entidad="reserva", entidad_id=reserva_id, ip=auditoria.ip_de(request))
    return reserva


@router.delete("/{reserva_id}")
def cancelar_reserva(
    reserva_id: int, request: Request,
    motivo: Optional[str] = Query(default=None, max_length=255, description="Motivo de la cancelación"),
    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user),
):
    uid = int(current_user["sub"])
    reserva = service.cancelar_reserva(db, reserva_id, current_user, motivo)
    _emitir(reserva, "reserva_cancelada", f"Reserva #{reserva_id} cancelada")
    notificaciones.avisar_reserva(db, reserva, "cancelada", reserva.motivo_cancelacion)  # al cliente
    if reserva.usuario_id == uid:   # canceló el cliente → también se avisa al restaurante
        notificaciones.avisar_reserva_al_restaurante(db, reserva, "cancelada",
                                                     reserva.motivo_cancelacion, excluir_usuario_id=uid)
    auditoria.registrar(db, "reserva_cancelada", usuario_id=uid, email=current_user["email"],
                        entidad="reserva", entidad_id=reserva_id, detalle=reserva.motivo_cancelacion,
                        ip=auditoria.ip_de(request))
    return {"message": "Reserva cancelada exitosamente", "motivo": reserva.motivo_cancelacion}

