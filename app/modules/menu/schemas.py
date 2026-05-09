from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ProductoCrear(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    precio: float
    categoria: Optional[str] = None
    imagen_url: Optional[str] = None

class ProductoActualizar(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    precio: Optional[float] = None
    categoria: Optional[str] = None
    imagen_url: Optional[str] = None
    disponible: Optional[bool] = None

class ProductoRespuesta(BaseModel):
    id: int
    nombre: str
    descripcion: Optional[str]
    precio: float
    categoria: Optional[str]
    imagen_url: Optional[str]
    disponible: bool
    creado_en: datetime

    class Config:
        from_attributes = True