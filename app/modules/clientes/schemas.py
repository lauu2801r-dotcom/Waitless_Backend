from typing import Optional

from pydantic import BaseModel, ConfigDict


class FavoritoRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    producto_id: int
    nombre: str
    precio: float
    categoria: Optional[str] = None
    disponible: bool = True


class ResumenCliente(BaseModel):
    visitas: int                       # pedidos pagados (facturas no anuladas)
    nivel: str                         # Bronce | Plata | Oro | Platino
    siguiente_nivel: Optional[str] = None
    visitas_siguiente: Optional[int] = None   # visitas necesarias para el siguiente nivel
    facturas: int
    favoritos: int
    calificacion_promedio: Optional[float] = None
    total_gastado: float
