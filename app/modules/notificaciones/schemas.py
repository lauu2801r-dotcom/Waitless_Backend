from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class NotificacionRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo: str
    titulo: str
    detalle: Optional[str] = None
    referencia_id: Optional[int] = None
    leida: bool
    creado_en: Optional[datetime] = None


class ContadorNotificaciones(BaseModel):
    no_leidas: int
