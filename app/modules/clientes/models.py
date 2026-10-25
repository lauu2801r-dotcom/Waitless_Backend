from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Favorito(Base):
    """Plato marcado como favorito por un cliente."""
    __tablename__ = "favoritos"
    __table_args__ = (UniqueConstraint("usuario_id", "producto_id", name="uq_favorito"),)

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False, index=True)
    creado_en = Column(DateTime, server_default=func.now())

    producto = relationship("Producto")
