from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, ForeignKey, Float, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum

class EstadoPedido(str, enum.Enum):
    pendiente = "pendiente"
    en_preparacion = "en_preparacion"
    listo = "listo"
    entregado = "entregado"
    cancelado = "cancelado"

class Pedido(Base):
    __tablename__ = "pedidos"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    mesa_id = Column(Integer, ForeignKey("mesas.id"), nullable=False)
    reserva_id = Column(Integer, ForeignKey("reservas.id"), nullable=True)
    estado = Column(Enum(EstadoPedido), default=EstadoPedido.pendiente)
    notas = Column(Text, nullable=True)
    total = Column(Float, default=0.0)
    creado_en = Column(DateTime, server_default=func.now())
    actualizado_en = Column(DateTime, onupdate=func.now())

    usuario = relationship("Usuario", backref="pedidos")
    mesa = relationship("Mesa", backref="pedidos")
    items = relationship("ItemPedido", backref="pedido", cascade="all, delete-orphan")

class ItemPedido(Base):
    __tablename__ = "items_pedido"

    id = Column(Integer, primary_key=True, index=True)
    pedido_id = Column(Integer, ForeignKey("pedidos.id"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    cantidad = Column(Integer, nullable=False, default=1)
    precio_unitario = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=False)
    notas = Column(String(255), nullable=True)

    producto = relationship("Producto", backref="items_pedido")