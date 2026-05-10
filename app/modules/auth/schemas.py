from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from app.modules.auth.models import RolUsuario

class UsuarioRegistro(BaseModel):
    nombre: str
    apellido: Optional[str] = ""
    email: EmailStr
    telefono: Optional[str] = None
    password: str

class UsuarioLogin(BaseModel):
    email: EmailStr
    password: str

class VerificarOTP(BaseModel):
    email: EmailStr
    otp: str

class ReenviarOTP(BaseModel):
    email: EmailStr

class UsuarioRespuesta(BaseModel):
    id: int
    nombre: str
    apellido: str
    email: str
    telefono: Optional[str]
    rol: RolUsuario
    verificado: bool
    creado_en: datetime

    class Config:
        from_attributes = True

class TokenRespuesta(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioRespuesta