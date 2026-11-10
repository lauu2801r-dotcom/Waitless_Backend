from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import enum

class RolUsuario(str, enum.Enum):
    cliente       = "cliente"
    empleado      = "empleado"
    administrador = "administrador"

class Usuario(Base):
    __tablename__ = "usuarios"

    id               = Column(Integer, primary_key=True, index=True)
    nombre           = Column(String(100), nullable=False)
    apellido         = Column(String(100), nullable=False)
    email            = Column(String(150), unique=True, index=True, nullable=False)
    telefono         = Column(String(20), nullable=True)
    hashed_password  = Column(String(255), nullable=False)
    rol              = Column(Enum(RolUsuario), default=RolUsuario.cliente)
    verificado       = Column(Boolean, default=False)
    otp_code         = Column(String(6), nullable=True)
    otp_expira       = Column(DateTime, nullable=True)
    otp_intentos     = Column(Integer, nullable=False, default=0, server_default="0")
    login_intentos   = Column(Integer, nullable=False, default=0, server_default="0")
    bloqueado_hasta  = Column(DateTime, nullable=True)
    # Consentimiento de tratamiento de datos (Ley 1581 de 2012)
    politica_version      = Column(String(10), nullable=True)
    politica_aceptada_en  = Column(DateTime, nullable=True)
    activo           = Column(Boolean, default=True)
    creado_en        = Column(DateTime, server_default=func.now())
    actualizado_en   = Column(DateTime, onupdate=func.now())

    # Solo para empleados: restaurante donde trabajan (los administradores usan Restaurante.administrador_id)
    restaurante_id   = Column(
        Integer,
        ForeignKey("restaurantes.id", use_alter=True, name="fk_usuario_restaurante"),
        nullable=True,
        index=True,
    )

    # Solo empleados: cargo (mesero, cocinero, cajero). Es una etiqueta, los permisos son los del rol.
    cargo            = Column(String(30), nullable=True)

    # Relación: un admin puede tener un restaurante
    restaurante = relationship(
        "Restaurante", back_populates="administrador", uselist=False,
        foreign_keys="Restaurante.administrador_id",
    )


class Restaurante(Base):
    __tablename__ = "restaurantes"

    id                = Column(Integer, primary_key=True, index=True)
    nombre            = Column(String(150), nullable=False)
    codigo_negocio    = Column(String(50), nullable=False)
    administrador_id  = Column(Integer, ForeignKey("usuarios.id"), unique=True, nullable=False)
    descripcion       = Column(String(255), nullable=True)
    tipo_cocina       = Column(String(100), nullable=True)
    emoji             = Column(String(10), nullable=True)
    direccion         = Column(String(200), nullable=True)
    telefono          = Column(String(30), nullable=True)
    instagram         = Column(String(100), nullable=True)
    horarios          = Column(Text, nullable=True)   # JSON: {"semana": {...}, "especiales": [...]}
    galeria           = Column(Text, nullable=True)   # JSON: lista de URLs de imágenes
    domicilio_activo  = Column(Boolean, nullable=True)    # None = activo (por defecto)
    costo_domicilio   = Column(Integer, nullable=True)    # None = 5000
    pedido_minimo_domicilio = Column(Integer, nullable=True)  # None = sin mínimo
    minutos_alerta_mesa = Column(Integer, nullable=True)   # tiempo máximo de una mesa ocupada antes de avisar (def. 90)
    activo            = Column(Boolean, nullable=False, default=True, server_default="1")
    creado_en         = Column(DateTime, server_default=func.now())
    actualizado_en    = Column(DateTime, onupdate=func.now())

    # Relación inversa
    administrador = relationship(
        "Usuario", back_populates="restaurante", foreign_keys=[administrador_id]
    )