import enum

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class TipoMovimiento(str, enum.Enum):
    entrada = "entrada"
    salida = "salida"


class Proveedor(Base):
    """Quien nos vende los insumos (HU-015)."""
    __tablename__ = "proveedores"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(150), unique=True, nullable=False)
    contacto = Column(String(150), nullable=True)
    telefono = Column(String(30), nullable=True)
    email = Column(String(150), nullable=True)
    productos_ofrecidos = Column(Text, nullable=True)
    condiciones = Column(Text, nullable=True)  # condiciones comerciales
    activo = Column(Boolean, default=True, nullable=False)
    creado_en = Column(DateTime, server_default=func.now())
    actualizado_en = Column(DateTime, onupdate=func.now())

    insumos = relationship("Insumo", back_populates="proveedor")


class Insumo(Base):
    """Ingrediente, bebida o material que el restaurante guarda en bodega (HU-014)."""
    __tablename__ = "insumos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(150), unique=True, nullable=False)
    categoria = Column(String(100), nullable=False, default="Ingredientes")
    unidad = Column(String(30), nullable=False, default="unidades")
    emoji = Column(String(10), nullable=True)
    stock_actual = Column(Float, nullable=False, default=0)
    stock_minimo = Column(Float, nullable=False, default=0)
    costo_unitario = Column(Float, nullable=False, default=0)
    proveedor_id = Column(Integer, ForeignKey("proveedores.id"), nullable=True)
    activo = Column(Boolean, default=True, nullable=False)
    creado_en = Column(DateTime, server_default=func.now())
    actualizado_en = Column(DateTime, onupdate=func.now())

    proveedor = relationship("Proveedor", back_populates="insumos")
    movimientos = relationship("MovimientoInventario", back_populates="insumo")

    # --- campos calculados (se incluyen en la respuesta de la API) ---
    @property
    def estado(self) -> str:
        """agotado: 0 | bajo: llegó al mínimo o menos | ok: todo bien"""
        if self.stock_actual <= 0:
            return "agotado"
        if self.stock_actual <= self.stock_minimo:
            return "bajo"
        return "ok"

    @property
    def valor(self) -> float:
        """Valor actual en bodega de este insumo."""
        return round(self.stock_actual * self.costo_unitario, 2)

    @property
    def proveedor_nombre(self):
        return self.proveedor.nombre if self.proveedor else None


class MovimientoInventario(Base):
    """Cada entrada o salida queda guardada y NO se borra (historial)."""
    __tablename__ = "movimientos_inventario"

    id = Column(Integer, primary_key=True, index=True)
    insumo_id = Column(Integer, ForeignKey("insumos.id"), nullable=False, index=True)
    tipo = Column(Enum(TipoMovimiento), nullable=False)
    cantidad = Column(Float, nullable=False)
    motivo = Column(String(255), nullable=True)
    stock_anterior = Column(Float, nullable=False)
    stock_resultante = Column(Float, nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    usuario_email = Column(String(150), nullable=True)
    creado_en = Column(DateTime, server_default=func.now(), index=True)

    insumo = relationship("Insumo", back_populates="movimientos")

    @property
    def insumo_nombre(self):
        return self.insumo.nombre if self.insumo else None

    @property
    def unidad(self):
        return self.insumo.unidad if self.insumo else None
