import enum
import json

from sqlalchemy import (
    Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.sql import func

from app.core.database import Base


class MetodoPago(str, enum.Enum):
    efectivo = "efectivo"
    tarjeta = "tarjeta"
    billetera = "billetera"        # billeteras digitales (Nequi, Daviplata…)
    transferencia = "transferencia"


class EstadoPago(str, enum.Enum):
    aprobado = "aprobado"
    rechazado = "rechazado"


class EstadoFactura(str, enum.Enum):
    pagada = "pagada"
    anulada = "anulada"


class Factura(Base):
    """Comprobante que se genera cuando un pago es aprobado (HU-016)."""
    __tablename__ = "facturas"

    id = Column(Integer, primary_key=True, index=True)
    numero = Column(String(20), unique=True, index=True, nullable=True)  # F-000001
    pedido_id = Column(Integer, ForeignKey("pedidos.id"), nullable=False, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)  # cliente

    subtotal = Column(Float, nullable=False)
    impuesto_pct = Column(Float, nullable=False, default=0)
    impuesto = Column(Float, nullable=False, default=0)
    propina = Column(Float, nullable=False, default=0)
    total = Column(Float, nullable=False)

    metodo = Column(Enum(MetodoPago), nullable=False)
    estado = Column(Enum(EstadoFactura), nullable=False, default=EstadoFactura.pagada)

    # Copia del pedido en el momento del pago (si el menú cambia, la factura no)
    detalle = Column(Text, nullable=True)

    pagado_en = Column(DateTime, server_default=func.now(), index=True)
    anulada_en = Column(DateTime, nullable=True)
    anulada_motivo = Column(String(255), nullable=True)
    anulada_por_email = Column(String(150), nullable=True)
    creado_en = Column(DateTime, server_default=func.now())

    # ---- datos calculados desde la copia guardada ----
    def _snap(self) -> dict:
        try:
            return json.loads(self.detalle or "{}")
        except ValueError:
            return {}

    @property
    def items(self) -> list:
        return self._snap().get("items", [])

    @property
    def concepto(self) -> str:
        return self._snap().get("concepto", "")

    @property
    def cliente_email(self):
        return self._snap().get("cliente_email")


class Pago(Base):
    """Cada intento de pago (aprobado o rechazado). Permite reintentar."""
    __tablename__ = "pagos"

    id = Column(Integer, primary_key=True, index=True)
    pedido_id = Column(Integer, ForeignKey("pedidos.id"), nullable=False, index=True)
    factura_id = Column(Integer, ForeignKey("facturas.id"), nullable=True)
    metodo = Column(Enum(MetodoPago), nullable=False)
    monto = Column(Float, nullable=False)
    estado = Column(Enum(EstadoPago), nullable=False)
    referencia = Column(String(40), nullable=True)      # id de la transacción
    motivo_rechazo = Column(String(255), nullable=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    usuario_email = Column(String(150), nullable=True)
    creado_en = Column(DateTime, server_default=func.now())
