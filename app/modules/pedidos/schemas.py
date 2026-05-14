# ══════════════════════════════════════════════════════════════
#  PARCHE — app/modules/pedidos/schemas.py
#  Añade tipo_entrega y direccion_domicilio al schema de pedidos
# ══════════════════════════════════════════════════════════════

from pydantic import BaseModel, model_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum
from app.modules.pedidos.models import EstadoPedido


# ── NUEVO ENUM ────────────────────────────────────────────────
class TipoEntrega(str, Enum):
    restaurante = "restaurante"
    domicilio   = "domicilio"


# ── SCHEMAS DE ÍTEMS (sin cambios) ───────────────────────────
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


# ── SCHEMA DE CREACIÓN — con tipo_entrega ────────────────────
class PedidoCrear(BaseModel):
    mesa_id: int
    reserva_id: Optional[int] = None
    items: List[ItemPedidoCrear]
    notas: Optional[str] = None

    # ── NUEVOS CAMPOS ──────────────────────────────────────
    tipo_entrega: TipoEntrega = TipoEntrega.restaurante
    direccion_domicilio: Optional[str] = None  # solo si tipo == domicilio

    @model_validator(mode='after')
    def validar_domicilio(self):
        """Si el pedido es a domicilio, la dirección es obligatoria."""
        if self.tipo_entrega == TipoEntrega.domicilio and not self.direccion_domicilio:
            raise ValueError(
                "La dirección de entrega es obligatoria para pedidos a domicilio."
            )
        return self


# ── SCHEMA DE ACTUALIZACIÓN ───────────────────────────────────
class PedidoActualizar(BaseModel):
    estado: Optional[EstadoPedido] = None
    notas: Optional[str] = None
    tipo_entrega: Optional[TipoEntrega] = None         # NUEVO
    direccion_domicilio: Optional[str] = None          # NUEVO


# ── SCHEMA DE RESPUESTA — con tipo_entrega ───────────────────
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

    # ── NUEVOS CAMPOS ──────────────────────────────────────
    tipo_entrega: TipoEntrega
    direccion_domicilio: Optional[str]

    class Config:
        from_attributes = True

class PedidoEditarItems(BaseModel):
    items: List[ItemPedidoCrear]
    notas: Optional[str] = None
    tipo_entrega: TipoEntrega = TipoEntrega.restaurante
    direccion_domicilio: Optional[str] = None

