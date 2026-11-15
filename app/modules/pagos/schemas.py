import re
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.modules.pagos.models import EstadoFactura, EstadoPago, MetodoPago


_REF_PORTAL = re.compile(r"^WLP-[A-Z0-9]{4,12}$")


def _referencia_valida(v: Optional[str]) -> Optional[str]:
    """Referencia que genera el portal de pago (WLP-XXXXXXXX). Si no tiene ese formato se ignora."""
    v = (v or "").strip().upper()
    return v if _REF_PORTAL.match(v) else None


class PagoCrear(BaseModel):
    pedido_id: int
    metodo: MetodoPago
    propina: float = 0
    # Solo para PRUEBAS: simula que la pasarela rechaza el pago (se ignora en producción)
    simular_rechazo: bool = False
    # Referencia de la transacción que mostró el portal de pago (opcional)
    referencia: Optional[str] = None

    @field_validator("referencia")
    @classmethod
    def referencia_portal(cls, v: Optional[str]) -> Optional[str]:
        return _referencia_valida(v)

    @field_validator("propina")
    @classmethod
    def propina_valida(cls, v: float) -> float:
        if v < 0:
            raise ValueError("La propina no puede ser negativa")
        return round(v, 2)


class PagoRechazoCrear(BaseModel):
    """El portal de pago rechazó el intento: se deja registrado (sin factura)."""
    pedido_id: int
    metodo: MetodoPago
    propina: float = 0
    referencia: Optional[str] = None
    motivo: Optional[str] = None

    @field_validator("propina")
    @classmethod
    def propina_valida(cls, v: float) -> float:
        if v < 0:
            raise ValueError("La propina no puede ser negativa")
        return round(v, 2)

    @field_validator("referencia")
    @classmethod
    def referencia_portal(cls, v: Optional[str]) -> Optional[str]:
        return _referencia_valida(v)

    @field_validator("motivo")
    @classmethod
    def motivo_corto(cls, v: Optional[str]) -> Optional[str]:
        v = (v or "").strip()
        return v[:200] if v else None


class AnularFactura(BaseModel):
    motivo: str

    @field_validator("motivo")
    @classmethod
    def motivo_valido(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Escribe el motivo de la anulación")
        return v


class FacturaResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    numero: Optional[str] = None
    pedido_id: int
    concepto: str
    restaurante: Optional[str] = None
    total: float
    metodo: MetodoPago
    estado: EstadoFactura
    pagado_en: Optional[datetime] = None


class ItemFactura(BaseModel):
    nombre: str
    cantidad: int
    precio_unitario: float
    subtotal: float


class FacturaDetalle(FacturaResumen):
    usuario_id: int
    cliente_email: Optional[str] = None
    subtotal: float
    impuesto_pct: float
    impuesto: float
    propina: float
    items: List[ItemFactura] = []
    anulada_en: Optional[datetime] = None
    anulada_motivo: Optional[str] = None
    anulada_por_email: Optional[str] = None


class PagoRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    pedido_id: int
    metodo: MetodoPago
    monto: float
    estado: EstadoPago
    referencia: Optional[str] = None
    motivo_rechazo: Optional[str] = None
    creado_en: Optional[datetime] = None
    factura: Optional[FacturaResumen] = None


class TotalMetodo(BaseModel):
    cantidad: int
    total: float


class ResumenVentas(BaseModel):
    periodo: str
    desde: datetime
    total_ventas: float
    total_facturas: int
    ticket_promedio: float
    anuladas: int
    por_cobrar: int
    por_metodo: Dict[str, TotalMetodo]


class PedidoPorCobrar(BaseModel):
    pedido_id: int
    concepto: str
    estado: str
    subtotal: float
    impuesto: float
    total_estimado: float
