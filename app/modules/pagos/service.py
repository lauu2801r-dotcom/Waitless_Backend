import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.modules.pagos.models import (
    EstadoFactura, EstadoPago, Factura, MetodoPago, Pago,
)
from app.modules.pagos.schemas import PagoCrear, PedidoPorCobrar, ResumenVentas, TotalMetodo
from app.modules.pedidos.models import EstadoPedido, ItemPedido, Pedido

logger = logging.getLogger("waitless.pagos")

# Impuesto al consumo de restaurantes en Colombia (8 %). Se puede cambiar con
# la variable de entorno IMPUESTO_PORCENTAJE sin tocar el código.
IMPUESTO_PORCENTAJE = float(os.getenv("IMPUESTO_PORCENTAJE", "8"))

# Colombia no tiene horario de verano: siempre UTC-5.
ZONA_CO = timezone(timedelta(hours=-5))


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _error(codigo: int, msg: str) -> HTTPException:
    return HTTPException(codigo, msg)


def _concepto(pedido: Pedido) -> str:
    tipo = getattr(pedido.tipo_entrega, "value", pedido.tipo_entrega)
    if tipo == "domicilio":
        return "Domicilio"
    return f"Mesa {pedido.mesa.numero}" if pedido.mesa else "Restaurante"


def _impuesto(subtotal: float) -> float:
    return round(subtotal * IMPUESTO_PORCENTAJE / 100)


def pedido_pagado(db: Session, pedido_id: int) -> bool:
    """¿El pedido ya tiene una factura pagada (no anulada)?"""
    return (
        db.query(Factura.id)
        .filter(Factura.pedido_id == pedido_id, Factura.estado == EstadoFactura.pagada)
        .first()
        is not None
    )


# ───────────────────────── Pasarela SIMULADA ─────────────────────────
def _pasarela_simulada(metodo: MetodoPago, simular_rechazo: bool) -> Tuple[bool, str, Optional[str]]:
    """
    Simula la respuesta de una pasarela de pagos (en producción real se
    reemplaza por la integración con Wompi, PayU, etc.).
    Nunca se reciben ni se guardan datos de tarjeta: solo el resultado.
    Devuelve (aprobado, referencia, motivo_rechazo).
    """
    if simular_rechazo and settings.ENVIRONMENT != "production":
        return False, "", "Pago rechazado por la entidad (simulado)"
    return True, f"SIM-{uuid.uuid4().hex[:10].upper()}", None


# ───────────────────────── Pagar ─────────────────────────
def pagar(db: Session, datos: PagoCrear, usuario_id: int, email: str, rol: str):
    """Procesa un pago. Devuelve (pago, factura o None si fue rechazado)."""
    pedido = (
        db.query(Pedido)
        .options(joinedload(Pedido.items).joinedload(ItemPedido.producto), joinedload(Pedido.mesa))
        .filter(Pedido.id == datos.pedido_id)
        .with_for_update(of=Pedido)
        .first()
    )
    if not pedido:
        raise _error(404, "Pedido no encontrado")

    es_personal = rol in ("administrador", "empleado")
    if not es_personal and pedido.usuario_id != usuario_id:
        raise _error(403, "No tienes permiso para pagar este pedido")
    if not es_personal and datos.metodo == MetodoPago.efectivo:
        raise _error(400, "El pago en efectivo lo registra el personal del restaurante")
    if pedido.estado == EstadoPedido.cancelado:
        raise _error(400, "El pedido está cancelado")
    if pedido_pagado(db, pedido.id):
        raise _error(400, "Este pedido ya está pagado")
    if not pedido.items or pedido.total <= 0:
        raise _error(400, "El pedido no tiene productos")

    subtotal = round(pedido.total, 2)
    impuesto = _impuesto(subtotal)
    total = round(subtotal + impuesto + datos.propina, 2)

    aprobado, referencia, motivo = _pasarela_simulada(datos.metodo, datos.simular_rechazo)
    pago = Pago(
        pedido_id=pedido.id, metodo=datos.metodo, monto=total,
        estado=EstadoPago.aprobado if aprobado else EstadoPago.rechazado,
        referencia=referencia or None, motivo_rechazo=motivo,
        usuario_id=usuario_id, usuario_email=email,
    )
    db.add(pago)

    factura = None
    if aprobado:
        snapshot = {
            "concepto": _concepto(pedido),
            "restaurante": pedido.restaurante.nombre if pedido.restaurante else None,
            "cliente_email": pedido.usuario.email if pedido.usuario else None,
            "items": [
                {
                    "nombre": it.producto.nombre if it.producto else f"Producto {it.producto_id}",
                    "cantidad": it.cantidad,
                    "precio_unitario": it.precio_unitario,
                    "subtotal": it.subtotal,
                }
                for it in pedido.items
            ],
        }
        factura = Factura(
            pedido_id=pedido.id, usuario_id=pedido.usuario_id,
            subtotal=subtotal, impuesto_pct=IMPUESTO_PORCENTAJE, impuesto=impuesto,
            propina=datos.propina, total=total, metodo=datos.metodo,
            estado=EstadoFactura.pagada, pagado_en=_ahora_utc(),
            detalle=json.dumps(snapshot, ensure_ascii=False),
        )
        db.add(factura)
        db.flush()
        factura.numero = f"F-{factura.id:06d}"
        pago.factura_id = factura.id

    db.commit()
    db.refresh(pago)
    if factura is not None:
        db.refresh(factura)
    return pago, factura


# ───────────────────────── Consultas ─────────────────────────
def listar_facturas(
    db: Session,
    usuario_id: Optional[int] = None,
    estado: Optional[EstadoFactura] = None,
    metodo: Optional[MetodoPago] = None,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
    restaurante_id: Optional[int] = None,
):
    q = db.query(Factura)
    if restaurante_id is not None:
        q = q.join(Pedido, Pedido.id == Factura.pedido_id).filter(Pedido.restaurante_id == restaurante_id)
    if usuario_id is not None:
        q = q.filter(Factura.usuario_id == usuario_id)
    if estado:
        q = q.filter(Factura.estado == estado)
    if metodo:
        q = q.filter(Factura.metodo == metodo)
    if desde:
        q = q.filter(Factura.pagado_en >= desde)
    if hasta:
        q = q.filter(Factura.pagado_en <= hasta)
    return q.order_by(Factura.pagado_en.desc(), Factura.id.desc()).offset(offset).limit(limit).all()


def obtener_factura(db: Session, factura_id: int) -> Factura:
    f = db.query(Factura).filter(Factura.id == factura_id).first()
    if not f:
        raise _error(404, "Factura no encontrada")
    return f


def pagos_de_pedido(db: Session, pedido_id: int) -> List[Pago]:
    return db.query(Pago).filter(Pago.pedido_id == pedido_id).order_by(Pago.id.desc()).all()


def anular_factura(db: Session, factura_id: int, motivo: str, email: str) -> Factura:
    f = obtener_factura(db, factura_id)
    if f.estado == EstadoFactura.anulada:
        raise _error(400, "La factura ya está anulada")
    f.estado = EstadoFactura.anulada
    f.anulada_en = _ahora_utc()
    f.anulada_motivo = motivo
    f.anulada_por_email = email
    db.commit()
    db.refresh(f)
    return f


def _inicio_periodo(periodo: str) -> datetime:
    """Inicio del periodo en hora de Colombia, convertido a UTC (como se guarda)."""
    ahora = datetime.now(ZONA_CO)
    hoy = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    if periodo == "hoy":
        inicio = hoy
    elif periodo == "semana":
        inicio = hoy - timedelta(days=6)
    elif periodo == "mes":
        inicio = hoy.replace(day=1)
    elif periodo == "anio":
        inicio = hoy.replace(month=1, day=1)
    else:
        raise _error(400, "Periodo inválido. Usa: hoy, semana, mes o anio")
    return inicio.astimezone(timezone.utc).replace(tzinfo=None)


def por_cobrar(db: Session, restaurante_id: Optional[int] = None) -> List[PedidoPorCobrar]:
    """Pedidos servidos (listo/entregado) que todavía no tienen factura pagada."""
    pagados = db.query(Factura.pedido_id).filter(Factura.estado == EstadoFactura.pagada)
    consulta = (
        db.query(Pedido)
        .options(joinedload(Pedido.items), joinedload(Pedido.mesa))
        .filter(
            Pedido.estado.in_([EstadoPedido.listo, EstadoPedido.entregado]),
            ~Pedido.id.in_(pagados),
        )
    )
    if restaurante_id is not None:
        consulta = consulta.filter(Pedido.restaurante_id == restaurante_id)
    pedidos = consulta.order_by(Pedido.id).all()
    resultado = []
    for p in pedidos:
        subtotal = round(p.total or 0, 2)
        imp = _impuesto(subtotal)
        resultado.append(PedidoPorCobrar(
            pedido_id=p.id, concepto=_concepto(p), estado=p.estado.value,
            subtotal=subtotal, impuesto=imp, total_estimado=round(subtotal + imp, 2),
        ))
    return resultado


def resumen(db: Session, periodo: str, restaurante_id: Optional[int] = None) -> ResumenVentas:
    desde = _inicio_periodo(periodo)
    q = db.query(Factura).filter(Factura.pagado_en >= desde)
    if restaurante_id is not None:
        q = q.join(Pedido, Pedido.id == Factura.pedido_id).filter(Pedido.restaurante_id == restaurante_id)
    facturas = q.all()
    pagadas = [f for f in facturas if f.estado == EstadoFactura.pagada]
    total = round(sum(f.total for f in pagadas), 2)
    por_metodo = {}
    for f in pagadas:
        m = f.metodo.value
        acc = por_metodo.setdefault(m, {"cantidad": 0, "total": 0.0})
        acc["cantidad"] += 1
        acc["total"] = round(acc["total"] + f.total, 2)
    return ResumenVentas(
        periodo=periodo, desde=desde, total_ventas=total, total_facturas=len(pagadas),
        ticket_promedio=round(total / len(pagadas), 2) if pagadas else 0.0,
        anuladas=len(facturas) - len(pagadas),
        por_cobrar=len(por_cobrar(db, restaurante_id)),
        por_metodo={k: TotalMetodo(**v) for k, v in por_metodo.items()},
    )


# ───────────────────────── Factura por correo ─────────────────────────
async def enviar_factura_email(factura_id: int):
    """
    Envía la factura al correo del cliente (en segundo plano). Usa su propia
    sesión de base de datos y nunca rompe el pago si el correo falla.
    """
    from fastapi_mail import FastMail, MessageSchema

    from app.core.database import SessionLocal
    from app.modules.auth.service import conf

    db = SessionLocal()
    try:
        f = db.query(Factura).filter(Factura.id == factura_id).first()
        if not f or not f.cliente_email:
            return
        filas = "".join(
            f"<tr><td>{i['nombre']}</td><td align='center'>{i['cantidad']}</td>"
            f"<td align='right'>${i['subtotal']:,.0f}</td></tr>"
            for i in f.items
        )
        cuerpo = f"""
        <h2>Gracias por tu pago · WaitLess</h2>
        <p>Factura <b>{f.numero}</b> · {f.concepto}</p>
        <table width="100%" cellpadding="4">{filas}</table>
        <hr>
        <p>Subtotal: ${f.subtotal:,.0f}<br>
        Impuesto ({f.impuesto_pct:g}%): ${f.impuesto:,.0f}<br>
        Propina: ${f.propina:,.0f}<br>
        <b>Total: ${f.total:,.0f}</b> ({f.metodo.value})</p>
        """
        mensaje = MessageSchema(
            subject=f"WaitLess - Factura {f.numero}",
            recipients=[f.cliente_email], body=cuerpo, subtype="html",
        )
        await FastMail(conf).send_message(mensaje)
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo enviar la factura %s por correo: %s", factura_id, e)
    finally:
        db.close()
