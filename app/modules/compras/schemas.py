from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.modules.compras.models import EstadoOrden


class ItemOrdenCrear(BaseModel):
    insumo_id: int
    cantidad: float
    costo_unitario: Optional[float] = None  # si no se envía, se usa el costo actual del insumo

    @field_validator("cantidad")
    @classmethod
    def cantidad_positiva(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("La cantidad debe ser mayor que 0")
        return v

    @field_validator("costo_unitario")
    @classmethod
    def costo_valido(cls, v):
        if v is not None and v < 0:
            raise ValueError("El costo no puede ser negativo")
        return v


def _sin_repetidos(items: List[ItemOrdenCrear]):
    ids = [i.insumo_id for i in items]
    if len(ids) != len(set(ids)):
        raise ValueError("Un mismo insumo no puede repetirse en la orden")


class OrdenCrear(BaseModel):
    proveedor_id: int
    fecha_entrega_esperada: Optional[date] = None
    notas: Optional[str] = None
    items: List[ItemOrdenCrear]

    @model_validator(mode="after")
    def validar(self):
        if not self.items:
            raise ValueError("La orden debe tener al menos un producto")
        _sin_repetidos(self.items)
        return self


class OrdenActualizar(BaseModel):
    """Solo se puede editar una orden que todavía está pendiente."""
    fecha_entrega_esperada: Optional[date] = None
    notas: Optional[str] = None
    items: Optional[List[ItemOrdenCrear]] = None

    @model_validator(mode="after")
    def validar(self):
        if self.items is not None:
            if not self.items:
                raise ValueError("La orden debe tener al menos un producto")
            _sin_repetidos(self.items)
        return self


class RecepcionItem(BaseModel):
    item_id: int
    cantidad: float

    @field_validator("cantidad")
    @classmethod
    def cantidad_positiva(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("La cantidad recibida debe ser mayor que 0")
        return v


class RecepcionCrear(BaseModel):
    items: List[RecepcionItem]
    notas: Optional[str] = None

    @model_validator(mode="after")
    def validar(self):
        if not self.items:
            raise ValueError("Indica qué productos llegaron")
        ids = [i.item_id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Un producto no puede repetirse en la recepción")
        return self


class ItemOrdenRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    insumo_id: int
    insumo_nombre: Optional[str] = None
    unidad: Optional[str] = None
    cantidad_pedida: float
    cantidad_recibida: float
    costo_unitario: float
    subtotal: float


class HistorialRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    estado: EstadoOrden
    detalle: Optional[str] = None
    usuario_email: Optional[str] = None
    creado_en: Optional[datetime] = None


class OrdenRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    proveedor_id: int
    proveedor_nombre: Optional[str] = None
    estado: EstadoOrden
    fecha_entrega_esperada: Optional[date] = None
    fecha_cumplimiento: Optional[datetime] = None
    notas: Optional[str] = None
    total: float
    creado_por_email: Optional[str] = None
    creado_en: Optional[datetime] = None
    items: List[ItemOrdenRespuesta]
    historial: List[HistorialRespuesta] = []


class OrdenResumen(BaseModel):
    """Versión corta para listados."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    proveedor_id: int
    proveedor_nombre: Optional[str] = None
    estado: EstadoOrden
    fecha_entrega_esperada: Optional[date] = None
    fecha_cumplimiento: Optional[datetime] = None
    total: float
    creado_en: Optional[datetime] = None


class MetricasProveedor(BaseModel):
    proveedor_id: int
    proveedor_nombre: str
    total_ordenes: int
    completas: int
    parciales: int
    pendientes: int
    canceladas: int
    entregas_a_tiempo: int
    cumplimiento_pct: float   # completas / (órdenes no canceladas)
    puntualidad_pct: Optional[float] = None  # None si ninguna orden tenía fecha esperada
    dias_promedio_entrega: Optional[float] = None
