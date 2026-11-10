from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.modules.restaurantes.horarios import Horarios


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
    direccion: Optional[str] = None
    telefono: Optional[str] = None
    instagram: Optional[str] = None
    horarios: Optional[dict] = None
    galeria: List[str] = []
    abierto_ahora: Optional[bool] = None   # None = sin horarios configurados
    minutos_alerta_mesa: int = 90
    domicilio_activo: bool = True
    costo_domicilio: int = 5000
    pedido_minimo_domicilio: int = 0


class RestauranteActualizar(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    tipo_cocina: Optional[str] = None
    emoji: Optional[str] = None
    direccion: Optional[str] = Field(default=None, max_length=200)
    telefono: Optional[str] = Field(default=None, max_length=30)
    instagram: Optional[str] = Field(default=None, max_length=100)
    horarios: Optional[Horarios] = None
    galeria: Optional[List[str]] = None
    minutos_alerta_mesa: Optional[int] = Field(default=None, ge=15, le=480)
    domicilio_activo: Optional[bool] = None
    costo_domicilio: Optional[int] = Field(default=None, ge=0, le=50000)
    pedido_minimo_domicilio: Optional[int] = Field(default=None, ge=0, le=500000)

    @field_validator("galeria")
    @classmethod
    def galeria_valida(cls, v):
        if v is None:
            return v
        if len(v) > 12:
            raise ValueError("Máximo 12 imágenes")
        limpias = []
        for u in v:
            u = (u or "").strip()
            if not u:
                continue
            if not u.lower().startswith(("https://", "http://")) or len(u) > 500:
                raise ValueError("Cada imagen debe ser un enlace http(s) de máximo 500 caracteres")
            limpias.append(u)
        return limpias

    @field_validator("telefono")
    @classmethod
    def telefono_valido(cls, v):
        if v is None or not v.strip():
            return None
        v = v.strip()
        if not all(c.isdigit() or c in "+ -()" for c in v) or sum(c.isdigit() for c in v) < 7:
            raise ValueError("Teléfono no válido")
        return v

    @field_validator("nombre")
    @classmethod
    def nombre_valido(cls, v):
        if v is not None:
            v = v.strip()
            if len(v) < 2:
                raise ValueError("El nombre debe tener al menos 2 caracteres")
        return v
