from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from app.core.database import Base


class Notificacion(Base):
    """Aviso para un usuario (pedido listo, pago aprobado, reserva, etc.)."""
    __tablename__ = "notificaciones"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    # pedido | pago | reserva | calificacion | promo | sistema
    tipo = Column(String(20), nullable=False, default="sistema")
    titulo = Column(String(150), nullable=False)
    detalle = Column(String(255), nullable=True)
    referencia_id = Column(Integer, nullable=True)  # id del pedido / factura / reserva
    leida = Column(Boolean, nullable=False, default=False, server_default="0")
    creado_en = Column(DateTime, server_default=func.now(), index=True)
