from sqlalchemy import event, Column, ForeignKey, Integer, String, Boolean, DateTime, Enum, UniqueConstraint
from sqlalchemy.sql import func
from app.core.database import Base
import enum
from datetime import datetime

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
    # HU-004: desde cuándo está ocupada y si ya se avisó que superó el tiempo máximo
    ocupada_desde = Column(DateTime, nullable=True)
    alerta_tiempo_enviada = Column(Boolean, nullable=False, default=False, server_default="0")
    creado_en = Column(DateTime, server_default=func.now())
    actualizado_en = Column(DateTime, onupdate=func.now())

    @property
    def minutos_ocupada(self):
        if self.ocupada_desde is None or getattr(self.estado, "value", self.estado) != "ocupada":
            return None
        return max(0, int((datetime.utcnow() - self.ocupada_desde).total_seconds() // 60))

    @property
    def alerta_tiempo(self):
        return bool(self.alerta_tiempo_enviada) and self.minutos_ocupada is not None


@event.listens_for(Mesa.estado, "set")
def _controlar_tiempo_ocupada(mesa, valor, anterior, _iniciador):
    """Se ejecuta SIEMPRE que cambia el estado, sin importar desde qué módulo (pedidos, mesas, reservas)."""
    nuevo = getattr(valor, "value", valor)
    antes = getattr(anterior, "value", anterior)
    if nuevo == "ocupada" and antes != "ocupada":
        mesa.ocupada_desde = datetime.utcnow()
        mesa.alerta_tiempo_enviada = False
    elif nuevo != "ocupada":
        mesa.ocupada_desde = None
        mesa.alerta_tiempo_enviada = False
