from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum
from sqlalchemy.sql import func
from app.core.database import Base
import enum

class RolUsuario(str, enum.Enum):
    cliente = "cliente"
    empleado = "empleado"
    administrador = "administrador"

class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    apellido = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    telefono = Column(String(20), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    rol = Column(Enum(RolUsuario), default=RolUsuario.cliente)
    verificado = Column(Boolean, default=False)
    otp_code = Column(String(6), nullable=True)
    otp_expira = Column(DateTime, nullable=True)
    activo = Column(Boolean, default=True)
    creado_en = Column(DateTime, server_default=func.now())
    actualizado_en = Column(DateTime, onupdate=func.now())