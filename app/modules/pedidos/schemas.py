from pydantic import BaseModel, model_validator
from typing import Optional, List
from datetime import datetime
from app.modules.pedidos.models import EstadoPedido

class ItemPedidoCrear(BaseModel):
    producto_id: int
    cantidad: int
    notas: Optional[str] = None

class ItemPedidoRespuesta(BaseModel):
    id: int
    producto_id: int
    nombre_producto: Optional[str] = None
    cantidad: int
    precio_unitario: float
    subtotal: float
    notas: Optional[str]

    @model_validator(mode='before')
    @classmethod
    def extraer_nombre(cls, values):
        if hasattr(values, 'producto') and values.producto:
            values.__dict__['nombre_producto'] = values.producto.nombre
        return values

    class Config:
        from_attributes = True

class PedidoCrear(BaseModel):
    mesa_id: int
    reserva_id: Optional[int] = None
    items: List[ItemPedidoCrear]
    notas: Optional[str] = None

class PedidoActualizar(BaseModel):
    estado: Optional[EstadoPedido] = None
    notas: Optional[str] = None

class PedidoRespuesta(BaseModel):
    id: int
    usuario_id: int
    mesa_id: int
    reserva_id: Optional[int]
    estado: EstadoPedido
    notas: Optional[str]
    total: float
    items: List[ItemPedidoRespuesta]
    creado_en: datetime

    class Config:
        from_attributes = True