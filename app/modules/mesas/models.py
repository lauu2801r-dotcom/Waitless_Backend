from sqlalchemy import Column, ForeignKey, Integer, String, Boolean, DateTime, Enum, UniqueConstraint
from sqlalchemy.sql import func
from app.core.database import Base
import enum

class EstadoMesa(str, enum.Enum):
    libre = "libre"
    ocupada = "ocupada"
    reservada = "reservada"
    en_limpieza = "en_limpieza"

class Mesa(Base):
    __tablename__ = "mesas"
    __table_args__ = (UniqueConstraint("restaurante_id", "numero", name="uq_mesa_restaurante_numero"),)

    id = Column(Integer, primary_key=True, index=True)
    numero = Column(Integer, nullable=False)
    restaurante_id = Column(Integer, ForeignKey("restaurantes.id"), nullable=True, index=True)
    capacidad = Column(Integer, nullable=False)
    estado = Column(Enum(EstadoMesa), default=EstadoMesa.libre)
    ubicacion = Column(String(100), nullable=True)
    activa = Column(Boolean, default=True)
    creado_en = Column(DateTime, server_default=func.now())
    actualizado_en = Column(DateTime, onupdate=func.now())