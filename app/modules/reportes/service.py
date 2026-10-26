from typing import Optional

from sqlalchemy import desc, func
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.modules.menu.models import Producto
from app.modules.mesas.models import EstadoMesa, Mesa
from app.modules.pedidos.models import EstadoPedido, ItemPedido, Pedido


def obtener_dashboard(db: Session, restaurante_id: Optional[int] = None):
    """Métricas del día. Si se indica restaurante_id, solo cuenta ese restaurante."""
    # "Hoy" = el día en Colombia (UTC-5). Los pedidos se guardan en UTC.
    ahora = datetime.utcnow()
    inicio_co = (ahora - timedelta(hours=5)).replace(hour=0, minute=0, second=0, microsecond=0)
    inicio = inicio_co + timedelta(hours=5)
    fin = inicio + timedelta(days=1)
    hoy_pedido = (Pedido.creado_en >= inicio, Pedido.creado_en < fin)

    def de_restaurante(q, columna):
        return q.filter(columna == restaurante_id) if restaurante_id is not None else q

    # ── Ventas hoy (solo pedidos entregados) ──
    ventas_hoy = de_restaurante(
        db.query(func.sum(Pedido.total)).filter(
            *hoy_pedido,
            Pedido.estado == EstadoPedido.entregado,
        ),
        Pedido.restaurante_id,
    ).scalar() or 0.0

    # ── Pedidos activos (pendiente + en_preparacion + listo) ──
    pedidos_activos = de_restaurante(
        db.query(func.count(Pedido.id)).filter(
            Pedido.estado.in_([
                EstadoPedido.pendiente,
                EstadoPedido.en_preparacion,
                EstadoPedido.listo,
            ])
        ),
        Pedido.restaurante_id,
    ).scalar() or 0

    # ── Mesas ──
    mesas_ocupadas = de_restaurante(
        db.query(func.count(Mesa.id)).filter(Mesa.estado == EstadoMesa.ocupada),
        Mesa.restaurante_id,
    ).scalar() or 0

    total_mesas = de_restaurante(
        db.query(func.count(Mesa.id)).filter(Mesa.activa == True),  # noqa: E712
        Mesa.restaurante_id,
    ).scalar() or 0

    # ── Clientes hoy (usuarios únicos con pedido hoy) ──
    clientes_hoy = de_restaurante(
        db.query(func.count(func.distinct(Pedido.usuario_id))).filter(
            *hoy_pedido,
            Pedido.estado != EstadoPedido.cancelado,
        ),
        Pedido.restaurante_id,
    ).scalar() or 0

    # ── Pedidos recientes (últimos 5 no cancelados) con su detalle ──
    recientes_raw = de_restaurante(
        db.query(Pedido).filter(Pedido.estado != EstadoPedido.cancelado),
        Pedido.restaurante_id,
    ).order_by(desc(Pedido.creado_en)).limit(5).all()

    pedidos_recientes = []
    for p in recientes_raw:
        items = []
        for it in db.query(ItemPedido).filter(ItemPedido.pedido_id == p.id).all():
            prod = db.query(Producto).filter(Producto.id == it.producto_id).first()
            items.append({
                "nombre": prod.nombre if prod else f"Producto #{it.producto_id}",
                "cantidad": it.cantidad,
                "subtotal": it.subtotal,
            })
        mesa = db.query(Mesa).filter(Mesa.id == p.mesa_id).first()
        pedidos_recientes.append({
            "id": p.id,
            "mesa_id": p.mesa_id,
            "mesa_numero": mesa.numero if mesa else None,
            "total": p.total,
            "estado": p.estado.value,
            "hace_minutos": max(0, int((ahora - p.creado_en).total_seconds() / 60)),
            "notas": p.notas,
            "items": items,
        })

    # ── Top platos del día ──
    top_q = db.query(
        Producto.id,
        Producto.nombre,
        func.sum(ItemPedido.cantidad).label("vendidos"),
        func.sum(ItemPedido.subtotal).label("ingresos"),
    ).join(ItemPedido, ItemPedido.producto_id == Producto.id)\
     .join(Pedido, Pedido.id == ItemPedido.pedido_id)\
     .filter(
        *hoy_pedido,
        Pedido.estado != EstadoPedido.cancelado,
    )
    top_q = de_restaurante(top_q, Pedido.restaurante_id)
    top_platos_raw = top_q.group_by(Producto.id, Producto.nombre)\
        .order_by(desc("vendidos")).limit(5).all()

    top_platos = [
        {
            "producto_id": row.id,
            "nombre": row.nombre,
            "vendidos": int(row.vendidos),
            "ingresos": float(row.ingresos),
        }
        for row in top_platos_raw
    ]

    return {
        "ventas_hoy": ventas_hoy,
        "pedidos_activos": pedidos_activos,
        "mesas_ocupadas": mesas_ocupadas,
        "total_mesas": total_mesas,
        "clientes_hoy": clientes_hoy,
        "pedidos_recientes": pedidos_recientes,
        "top_platos": top_platos,
    }
