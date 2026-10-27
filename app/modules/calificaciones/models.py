from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Calificacion(Base):
    """Estrellas (1 a 5) que un cliente le pone a un plato de un pedido pagado."""
    __tablename__ = "calificaciones"
    __table_args__ = (
        UniqueConstraint("usuario_id", "pedido_id", "producto_id", name="uq_calificacion_unica"),
    )

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    pedido_id = Column(Integer, ForeignKey("pedidos.id"), nullable=False, index=True)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False, index=True)
    restaurante_id = Column(Integer, ForeignKey("restaurantes.id"), nullable=True, index=True)
    estrellas = Column(Integer, nullable=False)
    comentario = Column(String(300), nullable=True)
    creado_en = Column(DateTime, server_default=func.now(), index=True)

    usuario = relationship("Usuario", lazy="joined")
    producto = relationship("Producto", lazy="joined")
