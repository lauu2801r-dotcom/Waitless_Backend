from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.modules.reservas.models import EstadoReserva


class ReservaCrear(BaseModel):
    mesa_id: int
    fecha_hora: datetime
    numero_personas: int = Field(ge=1, le=50)
    notas: Optional[str] = Field(default=None, max_length=500)


class ReservaActualizar(BaseModel):
    """El cliente puede cambiar fecha, personas y notas; solo el personal cambia el estado."""
    fecha_hora: Optional[datetime] = None
    numero_personas: Optional[int] = Field(default=None, ge=1, le=50)
    estado: Optional[EstadoReserva] = None
    notas: Optional[str] = Field(default=None, max_length=500)


class ReservaRespuesta(BaseModel):
    id: int
    usuario_id: int
    mesa_id: int
    mesa_numero: Optional[int] = None
    restaurante_id: Optional[int] = None
    cliente_nombre: Optional[str] = None
    fecha_hora: datetime
    numero_personas: int
    estado: EstadoReserva
    notas: Optional[str]
    tiempo_espera_estimado: Optional[int]
    motivo_cancelacion: Optional[str] = None
    creado_en: datetime

    class Config:
        from_attributes = True
