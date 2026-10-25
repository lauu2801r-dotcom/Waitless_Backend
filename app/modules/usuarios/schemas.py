import enum
import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.auth.models import RolUsuario


class RolAsignable(str, enum.Enum):
    """Roles que un administrador puede asignar (el rol administrador no se asigna)."""
    cliente = "cliente"
    empleado = "empleado"


def _validar_password(valor: str) -> str:
    if len(valor) < 8:
        raise ValueError("La contraseña debe tener mínimo 8 caracteres")
    if not re.search(r"[A-Z]", valor):
        raise ValueError("La contraseña debe tener al menos una mayúscula")
    if not re.search(r"[0-9]", valor):
        raise ValueError("La contraseña debe tener al menos un número")
    return valor


class EmpleadoCrear(BaseModel):
    nombre: str = Field(min_length=2, max_length=100)
    apellido: str = Field(min_length=1, max_length=100)
    email: EmailStr
    telefono: Optional[str] = Field(default=None, max_length=20)
    password: str

    @field_validator("password")
    @classmethod
    def password_segura(cls, v: str) -> str:
        return _validar_password(v)


class UsuarioActualizar(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=2, max_length=100)
    apellido: Optional[str] = Field(default=None, min_length=1, max_length=100)
    telefono: Optional[str] = Field(default=None, max_length=20)
    rol: Optional[RolAsignable] = None
    activo: Optional[bool] = None


class UsuarioGestionRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    apellido: str
    email: str
    telefono: Optional[str] = None
    rol: RolUsuario
    verificado: bool
    activo: bool
    creado_en: Optional[datetime] = None
