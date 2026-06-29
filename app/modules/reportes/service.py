from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, date
from app.modules.pedidos.models import Pedido, ItemPedido, EstadoPedido
from app.modules.mesas.models import Mesa, EstadoMesa
from app.modules.menu.models import Producto

def obtener_dashboard(db: Session):
    hoy = date.today()

    # ── Ventas hoy (solo pedidos entregados) ──
    ventas_hoy = db.query(func.sum(Pedido.total)).filter(
        func.date(Pedido.creado_en) == hoy,
        Pedido.estado == EstadoPedido.entregado
    ).scalar() or 0.0

    # ── Pedidos activos (pendiente + en_preparacion + listo) ──
    pedidos_activos = db.query(func.count(Pedido.id)).filter(
        Pedido.estado.in_([
            EstadoPedido.pendiente,
            EstadoPedido.en_preparacion,
            EstadoPedido.listo,
        ])
    ).scalar() or 0

    # ── Mesas ──
    mesas_ocupadas = db.query(func.count(Mesa.id)).filter(
        Mesa.estado == EstadoMesa.ocupada
    ).scalar() or 0

    total_mesas = db.query(func.count(Mesa.id)).filter(
        Mesa.activa == True
    ).scalar() or 0

    # ── Clientes hoy (usuarios únicos con pedido hoy) ──
    clientes_hoy = db.query(func.count(func.distinct(Pedido.usuario_id))).filter(
        func.date(Pedido.creado_en) == hoy,
        Pedido.estado != EstadoPedido.cancelado
    ).scalar() or 0

    # ── Pedidos recientes (últimos 5 activos) ──
    pedidos_recientes_raw = db.query(Pedido).filter(
        Pedido.estado != EstadoPedido.cancelado
    ).order_by(desc(Pedido.creado_en)).limit(5).all()

    ahora = datetime.now()
    pedidos_recientes = [
        {
            "id": p.id,
            "mesa_id": p.mesa_id,
            "total": p.total,
            "estado": p.estado.value,
            "hace_minutos": max(0, int((ahora - p.creado_en).total_seconds() / 60)),
        }
        for p in pedidos_recientes_raw
    ]

    # ── Top platos del día ──
    top_platos_raw = db.query(
        Producto.id,
        Producto.nombre,
        func.sum(ItemPedido.cantidad).label("vendidos"),
        func.sum(ItemPedido.subtotal).label("ingresos"),
    ).join(ItemPedido, ItemPedido.producto_id == Producto.id)\
     .join(Pedido, Pedido.id == ItemPedido.pedido_id)\
     .filter(
        func.date(Pedido.creado_en) == hoy,
        Pedido.estado != EstadoPedido.cancelado
    ).group_by(Producto.id, Producto.nombre)\
     .order_by(desc("vendidos"))\
     .limit(5).all()

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