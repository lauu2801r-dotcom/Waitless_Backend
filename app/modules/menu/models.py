from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class Producto(Base):
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False)
    descripcion = Column(Text, nullable=True)
    precio = Column(Float, nullable=False)
    restaurante_id = Column(Integer, ForeignKey("restaurantes.id"), nullable=True, index=True)
    categoria = Column(String(100), nullable=True)
    imagen_url = Column(String(255), nullable=True)
    disponible = Column(Boolean, default=True)
    activo = Column(Boolean, default=True)
    creado_en = Column(DateTime, server_default=func.now())
    actualizado_en = Column(DateTime, onupdate=func.now())

    restaurante = relationship("Restaurante", lazy="joined")

    @property
    def restaurante_nombre(self):
        return self.restaurante.nombre if self.restaurante else None
