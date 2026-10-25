from datetime import date, datetime, timezone
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.modules.compras.models import (
    EstadoOrden, HistorialOrden, ItemOrden, OrdenCompra,
)
from app.modules.compras.schemas import (
    ItemOrdenCrear, MetricasProveedor, OrdenActualizar, OrdenCrear, RecepcionCrear,
)
from app.modules.inventario.models import (
    Insumo, MovimientoInventario, Proveedor, TipoMovimiento,
)


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _error(codigo: int, msg: str) -> HTTPException:
    return HTTPException(codigo, msg)


def _anotar(orden: OrdenCompra, detalle: str, usuario_id: int, email: str):
    orden.historial.append(HistorialOrden(
        estado=orden.estado, detalle=detalle, usuario_id=usuario_id, usuario_email=email,
    ))


def _armar_items(db: Session, items: List[ItemOrdenCrear]) -> List[ItemOrden]:
    resultado = []
    for it in items:
        insumo = db.query(Insumo).filter(Insumo.id == it.insumo_id).first()
        if not insumo or not insumo.activo:
            raise _error(400, f"El insumo {it.insumo_id} no existe o está desactivado")
        costo = it.costo_unitario if it.costo_unitario is not None else insumo.costo_unitario
        resultado.append(ItemOrden(
            insumo_id=insumo.id, cantidad_pedida=round(it.cantidad, 3),
            cantidad_recibida=0, costo_unitario=costo,
        ))
    return resultado


def crear_orden(db: Session, datos: OrdenCrear, usuario_id: int, email: str) -> OrdenCompra:
    prov = db.query(Proveedor).filter(Proveedor.id == datos.proveedor_id).first()
    if not prov:
        raise _error(400, "El proveedor indicado no existe")
    if not prov.activo:
        raise _error(400, "El proveedor está desactivado")
    if datos.fecha_entrega_esperada and datos.fecha_entrega_esperada < date.today():
        raise _error(400, "La fecha de entrega esperada no puede estar en el pasado")

    orden = OrdenCompra(
        proveedor_id=prov.id, estado=EstadoOrden.pendiente,
        fecha_entrega_esperada=datos.fecha_entrega_esperada, notas=datos.notas,
        creado_por_id=usuario_id, creado_por_email=email,
    )
    orden.items = _armar_items(db, datos.items)
    _anotar(orden, "Orden creada", usuario_id, email)
    db.add(orden)
    db.commit()
    db.refresh(orden)
    return orden


def listar_ordenes(
    db: Session,
    estado: Optional[EstadoOrden] = None,
    proveedor_id: Optional[int] = None,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
):
    q = db.query(OrdenCompra).options(joinedload(OrdenCompra.proveedor), joinedload(OrdenCompra.items))
    if estado:
        q = q.filter(OrdenCompra.estado == estado)
    if proveedor_id is not None:
        q = q.filter(OrdenCompra.proveedor_id == proveedor_id)
    if desde:
        q = q.filter(OrdenCompra.creado_en >= desde)
    if hasta:
        q = q.filter(OrdenCompra.creado_en <= hasta)
    return (
        q.order_by(OrdenCompra.creado_en.desc(), OrdenCompra.id.desc())
        .offset(offset).limit(limit).all()
    )


def obtener_orden(db: Session, orden_id: int) -> OrdenCompra:
    orden = db.query(OrdenCompra).filter(OrdenCompra.id == orden_id).first()
    if not orden:
        raise _error(404, "Orden de compra no encontrada")
    return orden


def actualizar_orden(
    db: Session, orden_id: int, datos: OrdenActualizar, usuario_id: int, email: str
) -> OrdenCompra:
    orden = obtener_orden(db, orden_id)
    if orden.estado != EstadoOrden.pendiente:
        raise _error(400, "Solo se puede editar una orden pendiente (sin recepciones)")
    cambios = datos.model_dump(exclude_unset=True)
    if cambios.get("fecha_entrega_esperada") and cambios["fecha_entrega_esperada"] < date.today():
        raise _error(400, "La fecha de entrega esperada no puede estar en el pasado")
    if "fecha_entrega_esperada" in cambios:
        orden.fecha_entrega_esperada = cambios["fecha_entrega_esperada"]
    if "notas" in cambios:
        orden.notas = cambios["notas"]
    if datos.items is not None:
        orden.items = _armar_items(db, datos.items)  # reemplaza (delete-orphan)
    _anotar(orden, "Orden modificada", usuario_id, email)
    db.commit()
    db.refresh(orden)
    return orden


def _recalcular_estado(orden: OrdenCompra):
    if all(i.cantidad_recibida >= i.cantidad_pedida for i in orden.items):
        orden.estado = EstadoOrden.completa
        orden.fecha_cumplimiento = _ahora_utc()
    elif any(i.cantidad_recibida > 0 for i in orden.items):
        orden.estado = EstadoOrden.parcial
    else:
        orden.estado = EstadoOrden.pendiente


def recibir_orden(
    db: Session, orden_id: int, datos: RecepcionCrear, usuario_id: int, email: str
) -> OrdenCompra:
    """
    Registra lo que llegó. Por cada producto:
      - sube la cantidad recibida de la orden,
      - crea una ENTRADA en el inventario (queda en el historial de movimientos),
      - actualiza el costo del insumo al de esta compra.
    Todo en una sola transacción: o se guarda todo o nada.
    """
    orden = (
        db.query(OrdenCompra).filter(OrdenCompra.id == orden_id).with_for_update().first()
    )
    if not orden:
        raise _error(404, "Orden de compra no encontrada")
    if orden.estado in (EstadoOrden.completa, EstadoOrden.cancelada):
        raise _error(400, f"La orden está {orden.estado.value}, no admite más recepciones")

    por_id = {i.id: i for i in orden.items}
    resumen = []
    for rec in datos.items:
        item = por_id.get(rec.item_id)
        if not item:
            raise _error(400, f"El producto {rec.item_id} no pertenece a esta orden")
        falta = round(item.cantidad_pedida - item.cantidad_recibida, 3)
        if rec.cantidad > falta + 1e-9:
            raise _error(
                400,
                f"De {item.insumo.nombre} solo faltan {falta} {item.insumo.unidad} "
                f"y se intentó recibir {round(rec.cantidad, 3)}",
            )
        insumo = db.query(Insumo).filter(Insumo.id == item.insumo_id).with_for_update().first()
        anterior = insumo.stock_actual
        nuevo = round(anterior + rec.cantidad, 3)
        insumo.stock_actual = nuevo
        if item.costo_unitario > 0:
            insumo.costo_unitario = item.costo_unitario
        item.cantidad_recibida = round(item.cantidad_recibida + rec.cantidad, 3)
        db.add(MovimientoInventario(
            insumo_id=insumo.id, tipo=TipoMovimiento.entrada, cantidad=round(rec.cantidad, 3),
            motivo=f"Recepción orden de compra #{orden.id}",
            stock_anterior=round(anterior, 3), stock_resultante=nuevo,
            usuario_id=usuario_id, usuario_email=email,
        ))
        resumen.append(f"{insumo.nombre} +{round(rec.cantidad, 3)} {insumo.unidad}")

    _recalcular_estado(orden)
    detalle = "Recibido: " + ", ".join(resumen)
    if datos.notas:
        detalle += f" ({datos.notas.strip()})"
    _anotar(orden, detalle[:255], usuario_id, email)
    db.commit()
    db.refresh(orden)
    return orden


def cancelar_orden(db: Session, orden_id: int, usuario_id: int, email: str) -> OrdenCompra:
    orden = obtener_orden(db, orden_id)
    if orden.estado in (EstadoOrden.completa, EstadoOrden.cancelada):
        raise _error(400, f"La orden ya está {orden.estado.value}")
    detalle = "Orden cancelada"
    if orden.estado == EstadoOrden.parcial:
        detalle += " (lo ya recibido se conserva en el inventario)"
    orden.estado = EstadoOrden.cancelada
    _anotar(orden, detalle, usuario_id, email)
    db.commit()
    db.refresh(orden)
    return orden


# ───────────────────────── Métricas de cumplimiento ─────────────────────────
def _metricas_de(prov: Proveedor, ordenes: List[OrdenCompra]) -> MetricasProveedor:
    cuenta = lambda e: sum(1 for o in ordenes if o.estado == e)  # noqa: E731
    completas = [o for o in ordenes if o.estado == EstadoOrden.completa]
    no_canceladas = len(ordenes) - cuenta(EstadoOrden.cancelada)

    con_fecha = [o for o in completas if o.fecha_entrega_esperada and o.fecha_cumplimiento]
    a_tiempo = sum(1 for o in con_fecha if o.fecha_cumplimiento.date() <= o.fecha_entrega_esperada)

    dias = [
        (o.fecha_cumplimiento - o.creado_en).total_seconds() / 86400
        for o in completas if o.fecha_cumplimiento and o.creado_en
    ]
    return MetricasProveedor(
        proveedor_id=prov.id, proveedor_nombre=prov.nombre,
        total_ordenes=len(ordenes), completas=len(completas),
        parciales=cuenta(EstadoOrden.parcial), pendientes=cuenta(EstadoOrden.pendiente),
        canceladas=cuenta(EstadoOrden.cancelada), entregas_a_tiempo=a_tiempo,
        cumplimiento_pct=round(100 * len(completas) / no_canceladas, 1) if no_canceladas else 0.0,
        puntualidad_pct=round(100 * a_tiempo / len(con_fecha), 1) if con_fecha else None,
        dias_promedio_entrega=round(sum(dias) / len(dias), 1) if dias else None,
    )


def metricas_proveedor(db: Session, proveedor_id: int) -> MetricasProveedor:
    prov = db.query(Proveedor).filter(Proveedor.id == proveedor_id).first()
    if not prov:
        raise _error(404, "Proveedor no encontrado")
    ordenes = db.query(OrdenCompra).filter(OrdenCompra.proveedor_id == proveedor_id).all()
    return _metricas_de(prov, ordenes)


def metricas_todos(db: Session) -> List[MetricasProveedor]:
    provs = db.query(Proveedor).order_by(Proveedor.nombre).all()
    todas = db.query(OrdenCompra).all()
    return [
        _metricas_de(p, [o for o in todas if o.proveedor_id == p.id])
        for p in provs
    ]
