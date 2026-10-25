import enum

from sqlalchemy import (
    Column, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class EstadoOrden(str, enum.Enum):
    pendiente = "pendiente"   # se pidió, todavía no llega nada
    parcial = "parcial"       # llegó una parte
    completa = "completa"     # llegó todo
    cancelada = "cancelada"


class OrdenCompra(Base):
    """Pedido de insumos a un proveedor (HU-015)."""
    __tablename__ = "ordenes_compra"

    id = Column(Integer, primary_key=True, index=True)
    proveedor_id = Column(Integer, ForeignKey("proveedores.id"), nullable=False, index=True)
    estado = Column(Enum(EstadoOrden), nullable=False, default=EstadoOrden.pendiente)
    fecha_entrega_esperada = Column(Date, nullable=True)
    fecha_cumplimiento = Column(DateTime, nullable=True)  # cuando quedó completa
    notas = Column(Text, nullable=True)
    creado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    creado_por_email = Column(String(150), nullable=True)
    creado_en = Column(DateTime, server_default=func.now())
    actualizado_en = Column(DateTime, onupdate=func.now())

    proveedor = relationship("Proveedor")
    items = relationship(
        "ItemOrden", back_populates="orden", cascade="all, delete-orphan",
        order_by="ItemOrden.id",
    )
    historial = relationship(
        "HistorialOrden", back_populates="orden", cascade="all, delete-orphan",
        order_by="HistorialOrden.id",
    )

    @property
    def proveedor_nombre(self):
        return self.proveedor.nombre if self.proveedor else None

    @property
    def total(self) -> float:
        return round(sum(i.subtotal for i in self.items), 2)


class ItemOrden(Base):
    __tablename__ = "items_orden_compra"

    id = Column(Integer, primary_key=True, index=True)
    orden_id = Column(Integer, ForeignKey("ordenes_compra.id"), nullable=False, index=True)
    insumo_id = Column(Integer, ForeignKey("insumos.id"), nullable=False)
    cantidad_pedida = Column(Float, nullable=False)
    cantidad_recibida = Column(Float, nullable=False, default=0)
    costo_unitario = Column(Float, nullable=False, default=0)

    orden = relationship("OrdenCompra", back_populates="items")
    insumo = relationship("Insumo")

    @property
    def insumo_nombre(self):
        return self.insumo.nombre if self.insumo else None

    @property
    def unidad(self):
        return self.insumo.unidad if self.insumo else None

    @property
    def subtotal(self) -> float:
        return round(self.cantidad_pedida * self.costo_unitario, 2)


class HistorialOrden(Base):
    """Quién hizo qué con la orden (creó, recibió, canceló…). No se borra."""
    __tablename__ = "historial_ordenes_compra"

    id = Column(Integer, primary_key=True, index=True)
    orden_id = Column(Integer, ForeignKey("ordenes_compra.id"), nullable=False, index=True)
    estado = Column(Enum(EstadoOrden), nullable=False)
    detalle = Column(String(255), nullable=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    usuario_email = Column(String(150), nullable=True)
    creado_en = Column(DateTime, server_default=func.now())

    orden = relationship("OrdenCompra", back_populates="historial")
