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
    mesa_id: Optional[int] = None   # obligatoria solo si es en restaurante
    reserva_id: Optional[int] = None
    items: List[ItemPedidoCrear]
    notas: Optional[str] = None

    # ── NUEVOS CAMPOS ──────────────────────────────────────
    tipo_entrega: TipoEntrega = TipoEntrega.restaurante
    direccion_domicilio: Optional[str] = None  # solo si tipo == domicilio
    telefono_contacto: Optional[str] = None
    indicaciones_domicilio: Optional[str] = None

    @model_validator(mode='after')
    def validar_entrega(self):
        """En restaurante hace falta la mesa; a domicilio, dirección y teléfono."""
        if self.tipo_entrega == TipoEntrega.domicilio:
            direccion = (self.direccion_domicilio or "").strip()
            if len(direccion) < 8:
                raise ValueError("Escribe la dirección de entrega completa (calle, número, barrio).")
            telefono = (self.telefono_contacto or "").strip()
            if sum(c.isdigit() for c in telefono) < 7 or not all(c.isdigit() or c in "+ -()" for c in telefono):
                raise ValueError("Escribe un teléfono de contacto válido para el domicilio.")
            if len((self.indicaciones_domicilio or "")) > 200:
                raise ValueError("Las indicaciones son muy largas (máximo 200 caracteres).")
        elif self.mesa_id is None:
            raise ValueError("Elige la mesa para pedir en el restaurante.")
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
    mesa_id: Optional[int] = None
    reserva_id: Optional[int]
    estado: EstadoPedido
    notas: Optional[str]
    total: float
    items: List[ItemPedidoRespuesta]
    creado_en: datetime
    restaurante_id: Optional[int] = None
    restaurante_nombre: Optional[str] = None
    mesa_numero: Optional[int] = None
    minutos_estimados: Optional[int] = None   # estimación de la IA al crear el pedido

    # ── NUEVOS CAMPOS ──────────────────────────────────────
    tipo_entrega: TipoEntrega
    direccion_domicilio: Optional[str]
    telefono_contacto: Optional[str] = None
    indicaciones_domicilio: Optional[str] = None
    costo_envio: Optional[float] = 0.0

    class Config:
        from_attributes = True

class PedidoEditarItems(BaseModel):
    items: List[ItemPedidoCrear]
    notas: Optional[str] = None
    tipo_entrega: Optional[TipoEntrega] = None   # se ignora: el tipo del pedido no cambia
    direccion_domicilio: Optional[str] = None
    telefono_contacto: Optional[str] = None
    indicaciones_domicilio: Optional[str] = None

