import re
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import datetime
import enum


class RolUsuario(str, enum.Enum):
    cliente       = "cliente"
    empleado      = "empleado"
    administrador = "administrador"


class UsuarioRegistro(BaseModel):
    nombre: str
    apellido: Optional[str] = ""
    email: EmailStr
    telefono: Optional[str] = None
    password: str
    rol: Optional[RolUsuario] = RolUsuario.cliente
    nombre_restaurante: Optional[str] = None
    codigo_negocio: Optional[str] = None
    # Debe ser true para poder registrarse (Ley 1581 de 2012)
    acepta_politica: bool = False

class UsuarioLogin(BaseModel):
    email: EmailStr
    password: str

class VerificarOTP(BaseModel):
    email: EmailStr
    otp: str

class ReenviarOTP(BaseModel):
    email: EmailStr

class OlvidePassword(BaseModel):
    email: EmailStr

class RestablecerPassword(BaseModel):
    email: EmailStr
    otp: str
    nueva_password: str

    @field_validator("nueva_password")
    @classmethod
    def _password_segura(cls, v: str) -> str:
        # Mismas reglas que la pantalla de registro
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres")
        if not re.search(r"[A-Z]", v):
            raise ValueError("La contraseña debe incluir al menos una mayúscula")
        if not re.search(r"[0-9]", v):
            raise ValueError("La contraseña debe incluir al menos un número")
        return v

class CambiarPassword(BaseModel):
    password_actual: str
    nueva_password: str

    @field_validator("nueva_password")
    @classmethod
    def _password_segura(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres")
        if not re.search(r"[A-Z]", v):
            raise ValueError("La contraseña debe incluir al menos una mayúscula")
        if not re.search(r"[0-9]", v):
            raise ValueError("La contraseña debe incluir al menos un número")
        return v


class UsuarioRespuesta(BaseModel):
    id: int
    nombre: str
    apellido: str
    email: str
    telefono: Optional[str]
    rol: RolUsuario
    verificado: bool
    creado_en: datetime
    nombre_restaurante: Optional[str] = None

    class Config:
        from_attributes = True

class TokenRespuesta(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioRespuesta