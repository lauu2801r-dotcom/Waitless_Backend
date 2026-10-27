from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class ItemCalificacion(BaseModel):
    producto_id: int
    estrellas: int = Field(ge=1, le=5)


class CalificacionCrear(BaseModel):
    pedido_id: int
    items: List[ItemCalificacion] = Field(min_length=1)
    comentario: Optional[str] = Field(default=None, max_length=300)

    @field_validator("comentario")
    @classmethod
    def limpiar(cls, v):
        v = (v or "").strip()
        return v or None


class CalificacionItemRespuesta(BaseModel):
    producto_id: int
    producto_nombre: str
    estrellas: int


class EstadoCalificacionPedido(BaseModel):
    pedido_id: int
    pagado: bool            # solo se califica un pedido ya pagado
    calificado: bool
    comentario: Optional[str] = None
    items: List[CalificacionItemRespuesta] = []


class PlatoCalificado(BaseModel):
    producto_id: int
    nombre: str
    promedio: float
    total: int


class CalificacionReciente(BaseModel):
    pedido_id: int
    cliente: str
    plato: str
    estrellas: int
    comentario: Optional[str] = None
    creado_en: Optional[datetime] = None


class ResumenCalificaciones(BaseModel):
    promedio: float
    total: int
    distribucion: Dict[str, int]       # {"1": n, ..., "5": n}
    mejores: List[PlatoCalificado]
    por_mejorar: List[PlatoCalificado]
    recientes: List[CalificacionReciente]
