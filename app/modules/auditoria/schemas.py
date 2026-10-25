from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AuditoriaRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_id: Optional[int] = None
    email: Optional[str] = None
    accion: str
    entidad: Optional[str] = None
    entidad_id: Optional[int] = None
    detalle: Optional[str] = None
    ip: Optional[str] = None
    creado_en: Optional[datetime] = None
