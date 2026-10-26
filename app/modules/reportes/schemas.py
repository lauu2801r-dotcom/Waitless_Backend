from pydantic import BaseModel
from typing import List, Optional


class TopPlato(BaseModel):
    producto_id: int
    nombre: str
    vendidos: int
    ingresos: float


class ItemReciente(BaseModel):
    nombre: str
    cantidad: int
    subtotal: float


class PedidoReciente(BaseModel):
    id: int
    mesa_id: int
    mesa_numero: Optional[int] = None
    total: float
    estado: str
    hace_minutos: int
    notas: Optional[str] = None
    items: List[ItemReciente] = []


class DashboardRespuesta(BaseModel):
    ventas_hoy: float
    pedidos_activos: int
    mesas_ocupadas: int
    total_mesas: int
    clientes_hoy: int
    pedidos_recientes: List[PedidoReciente]
    top_platos: List[TopPlato]
