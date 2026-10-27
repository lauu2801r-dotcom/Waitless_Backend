from typing import List, Optional

from pydantic import BaseModel, field_validator


class RestauranteRespuesta(BaseModel):
    id: int
    nombre: str
    descripcion: Optional[str] = None
    tipo_cocina: Optional[str] = None
    emoji: Optional[str] = None
    activo: bool = True
    total_platos: int = 0
    mesas_libres: int = 0
    categorias: List[str] = []
    calificacion_promedio: Optional[float] = None
    total_calificaciones: int = 0


class RestauranteActualizar(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    tipo_cocina: Optional[str] = None
    emoji: Optional[str] = None

    @field_validator("nombre")
    @classmethod
    def nombre_valido(cls, v):
        if v is not None:
            v = v.strip()
            if len(v) < 2:
                raise ValueError("El nombre debe tener al menos 2 caracteres")
        return v
