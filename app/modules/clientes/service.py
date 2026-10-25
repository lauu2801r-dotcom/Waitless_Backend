from typing import List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.modules.clientes.models import Favorito
from app.modules.clientes.schemas import FavoritoRespuesta, ResumenCliente
from app.modules.menu.models import Producto
from app.modules.pagos.models import EstadoFactura, Factura

# Niveles de fidelización según visitas (pedidos pagados)
NIVELES: List[Tuple[str, int]] = [("Bronce", 0), ("Plata", 5), ("Oro", 10), ("Platino", 20)]


def calcular_nivel(visitas: int) -> Tuple[str, Optional[str], Optional[int]]:
    """Devuelve (nivel actual, siguiente nivel, visitas que exige el siguiente)."""
    actual = NIVELES[0][0]
    siguiente: Optional[Tuple[str, int]] = None
    for i, (nombre, minimo) in enumerate(NIVELES):
        if visitas >= minimo:
            actual = nombre
            siguiente = NIVELES[i + 1] if i + 1 < len(NIVELES) else None
    return actual, (siguiente[0] if siguiente else None), (siguiente[1] if siguiente else None)


def resumen(db: Session, usuario_id: int) -> ResumenCliente:
    q = db.query(Factura).filter(Factura.usuario_id == usuario_id)
    facturas_pagadas = q.filter(Factura.estado == EstadoFactura.pagada)
    visitas = facturas_pagadas.count()
    gastado = (
        db.query(func.coalesce(func.sum(Factura.total), 0.0))
        .filter(Factura.usuario_id == usuario_id, Factura.estado == EstadoFactura.pagada)
        .scalar()
    )
    nivel, siguiente, meta = calcular_nivel(visitas)
    return ResumenCliente(
        visitas=visitas, nivel=nivel, siguiente_nivel=siguiente, visitas_siguiente=meta,
        facturas=q.count(),
        favoritos=db.query(Favorito).filter(Favorito.usuario_id == usuario_id).count(),
        calificacion_promedio=_calificacion_promedio(db, usuario_id),
        total_gastado=round(float(gastado or 0), 2),
    )


def _calificacion_promedio(db: Session, usuario_id: int) -> Optional[float]:
    """Se llena cuando exista el módulo de calificaciones (paso 9C)."""
    try:
        from app.modules.calificaciones.models import Calificacion  # type: ignore
    except ImportError:
        return None
    media = (
        db.query(func.avg(Calificacion.estrellas))
        .filter(Calificacion.usuario_id == usuario_id)
        .scalar()
    )
    return round(float(media), 1) if media is not None else None


def listar_favoritos(db: Session, usuario_id: int) -> List[FavoritoRespuesta]:
    filas = (
        db.query(Favorito)
        .options(joinedload(Favorito.producto))
        .filter(Favorito.usuario_id == usuario_id)
        .order_by(Favorito.id.desc())
        .all()
    )
    return [
        FavoritoRespuesta(
            producto_id=f.producto_id, nombre=f.producto.nombre, precio=f.producto.precio,
            categoria=f.producto.categoria, disponible=bool(f.producto.disponible),
        )
        for f in filas
        if f.producto is not None and f.producto.activo
    ]


def agregar_favorito(db: Session, usuario_id: int, producto_id: int) -> None:
    producto = db.query(Producto).filter(Producto.id == producto_id, Producto.activo.is_(True)).first()
    if not producto:
        raise HTTPException(404, "Producto no encontrado")
    existe = db.query(Favorito).filter(
        Favorito.usuario_id == usuario_id, Favorito.producto_id == producto_id
    ).first()
    if existe:
        return  # idempotente
    db.add(Favorito(usuario_id=usuario_id, producto_id=producto_id))
    try:
        db.commit()
    except IntegrityError:  # dos taps seguidos
        db.rollback()


def quitar_favorito(db: Session, usuario_id: int, producto_id: int) -> None:
    db.query(Favorito).filter(
        Favorito.usuario_id == usuario_id, Favorito.producto_id == producto_id
    ).delete()
    db.commit()
