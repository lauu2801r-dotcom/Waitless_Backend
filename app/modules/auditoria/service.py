import logging
from datetime import datetime
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Query, Session

from app.modules.auditoria.models import RegistroAuditoria

logger = logging.getLogger("waitless.auditoria")


def ip_de(request: Request) -> Optional[str]:
    """IP del cliente que hizo la petición."""
    return request.client.host if request.client else None


def registrar(
    db: Session,
    accion: str,
    *,
    usuario_id: Optional[int] = None,
    email: Optional[str] = None,
    entidad: Optional[str] = None,
    entidad_id: Optional[int] = None,
    detalle: Optional[str] = None,
    ip: Optional[str] = None,
) -> None:
    """
    Guarda un registro de auditoría en una sesión PROPIA (misma base de datos),
    así no interfiere con la transacción ni con los objetos de la petición.
    Si la auditoría falla, nunca tumba la operación del usuario.
    """
    try:
        with Session(bind=db.get_bind()) as sesion_auditoria:
            sesion_auditoria.add(
                RegistroAuditoria(
                    usuario_id=usuario_id,
                    email=email,
                    accion=accion,
                    entidad=entidad,
                    entidad_id=entidad_id,
                    detalle=detalle,
                    ip=ip,
                )
            )
            sesion_auditoria.commit()
    except Exception:
        logger.exception("No se pudo guardar el registro de auditoría")


def consultar(
    db: Session,
    usuario_id: Optional[int] = None,
    accion: Optional[str] = None,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
) -> Query:
    """Devuelve la consulta ya filtrada y ordenada (más reciente primero)."""
    q = db.query(RegistroAuditoria)
    if usuario_id is not None:
        q = q.filter(RegistroAuditoria.usuario_id == usuario_id)
    if accion:
        q = q.filter(RegistroAuditoria.accion == accion)
    if desde:
        q = q.filter(RegistroAuditoria.creado_en >= desde)
    if hasta:
        q = q.filter(RegistroAuditoria.creado_en <= hasta)
    return q.order_by(RegistroAuditoria.creado_en.desc(), RegistroAuditoria.id.desc())
