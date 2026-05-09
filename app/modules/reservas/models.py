from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum

class EstadoReserva(str, enum.Enum):
    pendiente = "pendiente"
    confirmada = "confirmada"
    cancelada = "cancelada"
    completada = "completada"

class Reserva(Base):
    __tablename__ = "reservas"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    mesa_id = Column(Integer, ForeignKey("mesas.id"), nullable=False)
    fecha_hora = Column(DateTime, nullable=False)
    numero_personas = Column(Integer, nullable=False)
    estado = Column(Enum(EstadoReserva), default=EstadoReserva.pendiente)
    notas = Column(Text, nullable=True)
    tiempo_espera_estimado = Column(Integer, nullable=True)
    creado_en = Column(DateTime, server_default=func.now())
    actualizado_en = Column(DateTime, onupdate=func.now())

    usuario = relationship("Usuario", backref="reservas")
    mesa = relationship("Mesa", backref="reservas")