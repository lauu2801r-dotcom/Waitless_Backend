from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import admin_o_empleado, es_personal, get_current_user
from app.modules.reservas import service
from app.modules.reservas.schemas import (
    ReservaActualizar,
    ReservaCrear,
    ReservaRespuesta,
)

router = APIRouter()


@router.post("/", response_model=ReservaRespuesta)
def crear_reserva(
    datos: ReservaCrear,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return service.crear_reserva(db, datos, int(current_user["sub"]))


@router.get("/mis-reservas", response_model=List[ReservaRespuesta])
def mis_reservas(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return service.obtener_reservas(db, int(current_user["sub"]))


@router.get("/todas", response_model=List[ReservaRespuesta])
def todas_reservas(
    db: Session = Depends(get_db),
    current_user: dict = Depends(admin_o_empleado),
):
    return service.obtener_todas_reservas(db)


@router.get("/{reserva_id}", response_model=ReservaRespuesta)
def obtener_reserva(
    reserva_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    reserva = service.obtener_reserva(db, reserva_id)
    if not es_personal(current_user) and reserva.usuario_id != int(current_user["sub"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para ver esta reserva",
        )
    return reserva


@router.patch("/{reserva_id}", response_model=ReservaRespuesta)
def actualizar_reserva(
    reserva_id: int,
    datos: ReservaActualizar,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return service.actualizar_reserva(db, reserva_id, datos, int(current_user["sub"]))


@router.delete("/{reserva_id}")
def cancelar_reserva(
    reserva_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return service.cancelar_reserva(db, reserva_id, int(current_user["sub"]))
