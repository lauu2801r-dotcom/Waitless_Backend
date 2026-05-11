from pydantic import BaseModel
from typing import List

class TopPlato(BaseModel):
    producto_id: int
    nombre: str
    vendidos: int
    ingresos: float

class PedidoReciente(BaseModel):
    id: int
    mesa_id: int
    total: float
    estado: str
    hace_minutos: int

class DashboardRespuesta(BaseModel):
    ventas_hoy: float
    pedidos_activos: int
    mesas_ocupadas: int
    total_mesas: int
    clientes_hoy: int
    pedidos_recientes: List[PedidoReciente]
    top_platos: List[TopPlato]