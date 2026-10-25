from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


class RegistroAuditoria(Base):
    """
    Bitácora de acciones críticas (HU Registro de Acciones Críticas, RD-004).
    Es solo de inserción: no hay endpoints para editar ni borrar registros.
    """

    __tablename__ = "auditoria"

    id          = Column(Integer, primary_key=True, index=True)
    usuario_id  = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"),
                         nullable=True, index=True)
    email       = Column(String(150), nullable=True)      # útil en logins fallidos
    accion      = Column(String(60), nullable=False, index=True)
    entidad     = Column(String(50), nullable=True)       # ej. "pedido", "reserva"
    entidad_id  = Column(Integer, nullable=True)
    detalle     = Column(Text, nullable=True)
    ip          = Column(String(45), nullable=True)
    creado_en   = Column(DateTime, server_default=func.now(), index=True)
