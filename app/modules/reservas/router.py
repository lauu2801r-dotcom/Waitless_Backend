from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.core.security import verify_token
from app.modules.reservas import service
from app.modules.reservas.schemas import (
    ReservaCrear,
    ReservaActualizar,
    ReservaRespuesta
)
from fastapi import HTTPException, status

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

@router.post("/", response_model=ReservaRespuesta)
def crear_reserva(
    datos: ReservaCrear,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return service.crear_reserva(db, datos, int(current_user["sub"]))

@router.get("/mis-reservas", response_model=List[ReservaRespuesta])
def mis_reservas(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return service.obtener_reservas(db, int(current_user["sub"]))

@router.get("/todas", response_model=List[ReservaRespuesta])
def todas_reservas(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return service.obtener_todas_reservas(db)

@router.get("/{reserva_id}", response_model=ReservaRespuesta)
def obtener_reserva(
    reserva_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return service.obtener_reserva(db, reserva_id)

@router.patch("/{reserva_id}", response_model=ReservaRespuesta)
def actualizar_reserva(
    reserva_id: int,
    datos: ReservaActualizar,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return service.actualizar_reserva(db, reserva_id, datos, int(current_user["sub"]))

@router.delete("/{reserva_id}")
def cancelar_reserva(
    reserva_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return service.cancelar_reserva(db, reserva_id, int(current_user["sub"]))