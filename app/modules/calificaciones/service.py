from typing import Dict, Iterable, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.calificaciones.models import Calificacion
from app.modules.menu.models import Producto
from app.modules.calificaciones.schemas import (
    CalificacionCrear, CalificacionItemRespuesta, CalificacionReciente,
    EstadoCalificacionPedido, PlatoCalificado, ResumenCalificaciones,
)
from app.modules.pagos.service import pedido_pagado
from app.modules.pedidos.models import Pedido


def _redondear(v: Optional[float]) -> float:
    return round(float(v), 1) if v is not None else 0.0


# ───────────── Promedios (menú y restaurantes) ─────────────
def promedios_por_producto(db: Session, producto_ids: Iterable[int]) -> Dict[int, Tuple[float, int]]:
    ids = list(set(producto_ids))
    if not ids:
        return {}
    filas = (
        db.query(Calificacion.producto_id, func.avg(Calificacion.estrellas), func.count(Calificacion.id))
        .filter(Calificacion.producto_id.in_(ids))
        .group_by(Calificacion.producto_id)
        .all()
    )
    return {pid: (_redondear(avg), int(n)) for pid, avg, n in filas}


def adjuntar_a_productos(db: Session, productos) -> None:
    """Agrega calificacion_promedio y total_calificaciones a cada producto del menú."""
    datos = promedios_por_producto(db, [p.id for p in productos])
    for p in productos:
        prom, total = datos.get(p.id, (None, 0))
        p.calificacion_promedio = prom
        p.total_calificaciones = total


def promedio_restaurante(db: Session, restaurante_id: int) -> Tuple[Optional[float], int]:
    avg, n = (
        db.query(func.avg(Calificacion.estrellas), func.count(Calificacion.id))
        .filter(Calificacion.restaurante_id == restaurante_id)
        .one()
    )
    return (_redondear(avg) if n else None), int(n or 0)


# ───────────── Calificar ─────────────
def _pedido_del_usuario(db: Session, pedido_id: int, usuario_id: int) -> Pedido:
    pedido = db.query(Pedido).filter(Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pedido no encontrado")
    if pedido.usuario_id != usuario_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo puedes calificar tus propios pedidos")
    return pedido


def estado_del_pedido(db: Session, pedido_id: int, usuario_id: int) -> EstadoCalificacionPedido:
    _pedido_del_usuario(db, pedido_id, usuario_id)
    filas = (
        db.query(Calificacion)
        .filter(Calificacion.pedido_id == pedido_id, Calificacion.usuario_id == usuario_id)
        .all()
    )
    return EstadoCalificacionPedido(
        pedido_id=pedido_id,
        pagado=pedido_pagado(db, pedido_id),
        calificado=bool(filas),
        comentario=next((f.comentario for f in filas if f.comentario), None),
        items=[
            CalificacionItemRespuesta(
                producto_id=f.producto_id,
                producto_nombre=f.producto.nombre if f.producto else "",
                estrellas=f.estrellas,
            )
            for f in filas
        ],
    )


def calificar(db: Session, datos: CalificacionCrear, usuario_id: int) -> EstadoCalificacionPedido:
    pedido = _pedido_del_usuario(db, datos.pedido_id, usuario_id)
    if not pedido_pagado(db, pedido.id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Puedes calificar cuando el pedido esté pagado")
    ya = db.query(Calificacion.id).filter(
        Calificacion.pedido_id == pedido.id, Calificacion.usuario_id == usuario_id
    ).first()
    if ya:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ya calificaste este pedido")

    del_pedido = {i.producto_id for i in pedido.items}
    vistos = set()
    for it in datos.items:
        if it.producto_id not in del_pedido:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ese plato no es parte de tu pedido")
        if it.producto_id in vistos:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Plato repetido en la calificación")
        vistos.add(it.producto_id)

    for it in datos.items:
        db.add(Calificacion(
            usuario_id=usuario_id, pedido_id=pedido.id, producto_id=it.producto_id,
            restaurante_id=pedido.restaurante_id, estrellas=it.estrellas,
            comentario=datos.comentario,
        ))
    db.commit()
    return estado_del_pedido(db, pedido.id, usuario_id)


# ───────────── Resumen para el administrador ─────────────
def resumen(db: Session, restaurante_id: Optional[int]) -> ResumenCalificaciones:
    base = db.query(Calificacion)
    if restaurante_id is not None:
        base = base.filter(Calificacion.restaurante_id == restaurante_id)

    avg, total = (
        base.with_entities(func.avg(Calificacion.estrellas), func.count(Calificacion.id)).one()
    )
    distribucion = {str(i): 0 for i in range(1, 6)}
    for estrellas, n in base.with_entities(Calificacion.estrellas, func.count(Calificacion.id)).group_by(
        Calificacion.estrellas
    ).all():
        distribucion[str(int(estrellas))] = int(n)

    por_plato = [
        PlatoCalificado(producto_id=pid, nombre=nombre, promedio=_redondear(p), total=int(n))
        for pid, nombre, p, n in base.join(Calificacion.producto)
        .with_entities(
            Calificacion.producto_id, Producto.nombre, func.avg(Calificacion.estrellas), func.count(Calificacion.id)
        )
        .group_by(Calificacion.producto_id, Producto.nombre)
        .all()
    ]
    mejores = sorted(por_plato, key=lambda x: (-x.promedio, -x.total))[:5]
    por_mejorar = [x for x in sorted(por_plato, key=lambda x: (x.promedio, -x.total)) if x.promedio < 4][:5]

    recientes = [
        CalificacionReciente(
            pedido_id=c.pedido_id,
            cliente=(f"{c.usuario.nombre} {c.usuario.apellido or ''}".strip() if c.usuario else "Cliente"),
            plato=c.producto.nombre if c.producto else "",
            estrellas=c.estrellas, comentario=c.comentario, creado_en=c.creado_en,
        )
        for c in base.order_by(Calificacion.id.desc()).limit(20).all()
    ]
    return ResumenCalificaciones(
        promedio=_redondear(avg) if total else 0.0, total=int(total or 0),
        distribucion=distribucion, mejores=mejores, por_mejorar=por_mejorar, recientes=recientes,
    )

