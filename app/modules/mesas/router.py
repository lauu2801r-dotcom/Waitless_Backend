from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.modules.mesas import service
from app.modules.mesas.models import EstadoMesa
from app.modules.mesas.schemas import (
    MesaCrear,
    MesaActualizar,
    MesaRespuesta
)

router = APIRouter()

@router.post("/", response_model=MesaRespuesta)
def crear_mesa(datos: MesaCrear, db: Session = Depends(get_db)):
    return service.crear_mesa(db, datos)

@router.get("/", response_model=List[MesaRespuesta])
def listar_mesas(db: Session = Depends(get_db)):
    return service.obtener_mesas(db)

@router.get("/disponibles", response_model=List[MesaRespuesta])
def mesas_disponibles(db: Session = Depends(get_db)):
    return service.obtener_mesas_disponibles(db)

@router.get("/{mesa_id}", response_model=MesaRespuesta)
def obtener_mesa(mesa_id: int, db: Session = Depends(get_db)):
    return service.obtener_mesa(db, mesa_id)

@router.patch("/{mesa_id}", response_model=MesaRespuesta)
def actualizar_mesa(
    mesa_id: int,
    datos: MesaActualizar,
    db: Session = Depends(get_db)
):
    return service.actualizar_mesa(db, mesa_id, datos)

@router.patch("/{mesa_id}/estado", response_model=MesaRespuesta)
def cambiar_estado(
    mesa_id: int,
    estado: EstadoMesa,
    db: Session = Depends(get_db)
):
    return service.actualizar_estado_mesa(db, mesa_id, estado)

@router.delete("/{mesa_id}")
def eliminar_mesa(mesa_id: int, db: Session = Depends(get_db)):
    return service.eliminar_mesa(db, mesa_id)