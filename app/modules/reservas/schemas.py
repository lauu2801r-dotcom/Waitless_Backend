from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.modules.reservas.models import EstadoReserva

class ReservaCrear(BaseModel):
    mesa_id: int
    fecha_hora: datetime
    numero_personas: int
    notas: Optional[str] = None

class ReservaActualizar(BaseModel):
    fecha_hora: Optional[datetime] = None
    numero_personas: Optional[int] = None
    estado: Optional[EstadoReserva] = None
    notas: Optional[str] = None

class ReservaRespuesta(BaseModel):
    id: int
    usuario_id: int
    mesa_id: int
    fecha_hora: datetime
    numero_personas: int
    estado: EstadoReserva
    notas: Optional[str]
    tiempo_espera_estimado: Optional[int]
    creado_en: datetime

    class Config:
        from_attributes = True