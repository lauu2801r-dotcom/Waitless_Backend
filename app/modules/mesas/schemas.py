from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.modules.mesas.models import EstadoMesa

class MesaCrear(BaseModel):
    numero: int
    capacidad: int
    ubicacion: Optional[str] = None

class MesaActualizar(BaseModel):
    capacidad: Optional[int] = None
    estado: Optional[EstadoMesa] = None
    ubicacion: Optional[str] = None
    activa: Optional[bool] = None

class MesaRespuesta(BaseModel):
    id: int
    numero: int
    capacidad: int
    estado: EstadoMesa
    ubicacion: Optional[str]
    activa: bool
    creado_en: datetime

    class Config:
        from_attributes = True