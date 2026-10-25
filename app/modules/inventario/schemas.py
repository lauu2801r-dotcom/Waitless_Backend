from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from app.modules.inventario.models import TipoMovimiento


def _limpiar(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = v.strip()
    return v or None


# ───────────────────────── Proveedores ─────────────────────────
class ProveedorCrear(BaseModel):
    nombre: str
    contacto: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[EmailStr] = None
    productos_ofrecidos: Optional[str] = None
    condiciones: Optional[str] = None

    @field_validator("nombre")
    @classmethod
    def nombre_valido(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("El nombre del proveedor es obligatorio")
        return v


class ProveedorActualizar(BaseModel):
    nombre: Optional[str] = None
    contacto: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[EmailStr] = None
    productos_ofrecidos: Optional[str] = None
    condiciones: Optional[str] = None
    activo: Optional[bool] = None

    @field_validator("nombre")
    @classmethod
    def nombre_valido(cls, v):
        if v is None:
            return v
        v = v.strip()
        if len(v) < 2:
            raise ValueError("El nombre del proveedor es obligatorio")
        return v


class ProveedorRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    contacto: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    productos_ofrecidos: Optional[str] = None
    condiciones: Optional[str] = None
    activo: bool


# ───────────────────────── Insumos ─────────────────────────
class InsumoCrear(BaseModel):
    nombre: str
    categoria: str = "Ingredientes"
    unidad: str = "unidades"
    emoji: Optional[str] = None
    stock_inicial: float = 0
    stock_minimo: float = 0
    costo_unitario: float = 0
    proveedor_id: Optional[int] = None

    @field_validator("nombre", "categoria", "unidad")
    @classmethod
    def texto_obligatorio(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Este campo es obligatorio")
        return v

    @field_validator("stock_inicial", "stock_minimo", "costo_unitario")
    @classmethod
    def no_negativo(cls, v: float) -> float:
        if v < 0:
            raise ValueError("No puede ser negativo")
        return v


class InsumoActualizar(BaseModel):
    """El stock NO se cambia aquí: se cambia solo con movimientos (queda historial)."""
    nombre: Optional[str] = None
    categoria: Optional[str] = None
    unidad: Optional[str] = None
    emoji: Optional[str] = None
    stock_minimo: Optional[float] = None
    costo_unitario: Optional[float] = None
    proveedor_id: Optional[int] = None
    activo: Optional[bool] = None

    @field_validator("nombre", "categoria", "unidad")
    @classmethod
    def texto_no_vacio(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Este campo no puede quedar vacío")
        return v

    @field_validator("stock_minimo", "costo_unitario")
    @classmethod
    def no_negativo(cls, v):
        if v is not None and v < 0:
            raise ValueError("No puede ser negativo")
        return v


class InsumoRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    categoria: str
    unidad: str
    emoji: Optional[str] = None
    stock_actual: float
    stock_minimo: float
    costo_unitario: float
    valor: float
    estado: str  # ok | bajo | agotado
    proveedor_id: Optional[int] = None
    proveedor_nombre: Optional[str] = None
    activo: bool


# ───────────────────────── Movimientos ─────────────────────────
class MovimientoCrear(BaseModel):
    insumo_id: int
    tipo: TipoMovimiento
    cantidad: float
    motivo: Optional[str] = None

    @field_validator("cantidad")
    @classmethod
    def cantidad_positiva(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("La cantidad debe ser mayor que 0")
        return v

    @field_validator("motivo")
    @classmethod
    def motivo_limpio(cls, v):
        return _limpiar(v)


class MovimientoRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    insumo_id: int
    insumo_nombre: Optional[str] = None
    unidad: Optional[str] = None
    tipo: TipoMovimiento
    cantidad: float
    motivo: Optional[str] = None
    stock_anterior: float
    stock_resultante: float
    usuario_id: Optional[int] = None
    usuario_email: Optional[str] = None
    creado_en: Optional[datetime] = None


class ResumenInventario(BaseModel):
    total_insumos: int
    bajo_stock: int
    agotados: int
    valor_total: float
