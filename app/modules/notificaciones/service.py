import logging
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.notificaciones.models import Notificacion
from app.websocket.manager import manager

logger = logging.getLogger("waitless.notificaciones")

MAX_POR_USUARIO = 100  # se conservan las 100 más recientes de cada usuario


def crear(
    db: Session,
    usuario_id: Optional[int],
    tipo: str,
    titulo: str,
    detalle: Optional[str] = None,
    referencia_id: Optional[int] = None,
) -> None:
    """
    Guarda una notificación y la empuja por WebSocket al usuario.
    Es "best effort": si algo falla NO debe romper la operación principal
    (pagar, cambiar un pedido, etc.), por eso nunca lanza error.
    """
    if not usuario_id:
        return
    try:
        n = Notificacion(
            usuario_id=usuario_id, tipo=tipo, titulo=titulo[:150],
            detalle=(detalle or None) and detalle[:255], referencia_id=referencia_id,
        )
        db.add(n)
        db.commit()
        db.refresh(n)
        _podar(db, usuario_id)
        manager.emitir(f"usuario:{usuario_id}", {
            "tipo": "notificacion", "id": n.id, "categoria": tipo,
            "titulo": titulo, "detalle": detalle, "mensaje": titulo,
        })
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning("No se pudo crear la notificación (%s): %s", titulo, e)


def _podar(db: Session, usuario_id: int) -> None:
    try:
        sobrantes = (
            db.query(Notificacion.id)
            .filter(Notificacion.usuario_id == usuario_id)
            .order_by(Notificacion.id.desc())
            .offset(MAX_POR_USUARIO).all()
        )
        if sobrantes:
            ids = [s[0] for s in sobrantes]
            db.query(Notificacion).filter(Notificacion.id.in_(ids)).delete(synchronize_session=False)
            db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()


def listar(db: Session, usuario_id: int, solo_no_leidas: bool = False, limite: int = 50) -> List[Notificacion]:
    q = db.query(Notificacion).filter(Notificacion.usuario_id == usuario_id)
    if solo_no_leidas:
        q = q.filter(Notificacion.leida == False)  # noqa: E712
    return q.order_by(Notificacion.id.desc()).limit(limite).all()


def contar_no_leidas(db: Session, usuario_id: int) -> int:
    return (
        db.query(Notificacion)
        .filter(Notificacion.usuario_id == usuario_id, Notificacion.leida == False)  # noqa: E712
        .count()
    )


def _propia(db: Session, notificacion_id: int, usuario_id: int) -> Notificacion:
    n = db.query(Notificacion).filter(
        Notificacion.id == notificacion_id, Notificacion.usuario_id == usuario_id
    ).first()
    if not n:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notificación no encontrada")
    return n


def marcar_leida(db: Session, notificacion_id: int, usuario_id: int) -> Notificacion:
    n = _propia(db, notificacion_id, usuario_id)
    if not n.leida:
        n.leida = True
        db.commit()
        db.refresh(n)
    return n


def marcar_todas_leidas(db: Session, usuario_id: int) -> int:
    cantidad = (
        db.query(Notificacion)
        .filter(Notificacion.usuario_id == usuario_id, Notificacion.leida == False)  # noqa: E712
        .update({Notificacion.leida: True}, synchronize_session=False)
    )
    db.commit()
    return cantidad


def eliminar(db: Session, notificacion_id: int, usuario_id: int) -> None:
    n = _propia(db, notificacion_id, usuario_id)
    db.delete(n)
    db.commit()


# ───────────── Textos de las notificaciones (un solo lugar) ─────────────
def _dinero(v: float) -> str:
    return "$" + f"{round(v):,}".replace(",", ".")


def _lugar(pedido) -> str:
    """'Mesa 4' o 'Domicilio' según el tipo de pedido."""
    if getattr(getattr(pedido, "tipo_entrega", None), "value", getattr(pedido, "tipo_entrega", None)) == "domicilio":
        return "Domicilio"
    return f"Mesa {pedido.mesa_numero or pedido.mesa_id}"


def avisar_pedido_creado(db: Session, pedido) -> None:
    donde = pedido.restaurante_nombre or "el restaurante"
    crear(db, pedido.usuario_id, "pedido", f"Pedido #{pedido.id} recibido",
          f"{donde} · {_lugar(pedido)} · {_dinero(pedido.total)}", pedido.id)


def avisar_estado_pedido(db: Session, pedido) -> None:
    estado = getattr(pedido.estado, "value", pedido.estado)
    donde = pedido.restaurante_nombre or "el restaurante"
    lugar = _lugar(pedido)
    domicilio = lugar == "Domicilio"
    textos = {
        "en_preparacion": (f"Tu pedido #{pedido.id} está en preparación", f"{donde} ya está preparando tus platos."),
        "listo": (
            (f"¡Tu domicilio #{pedido.id} va en camino!", f"{donde} · {pedido.direccion_domicilio or 'tu dirección'}")
            if domicilio else (f"¡Tu pedido #{pedido.id} está listo!", f"{donde} · {lugar}")
        ),
        "entregado": (f"Pedido #{pedido.id} entregado", "Ya puedes pagarlo desde Mis pedidos."),
        "cancelado": (f"Pedido #{pedido.id} cancelado", f"{donde}"),
    }
    if estado in textos:
        titulo, detalle = textos[estado]
        crear(db, pedido.usuario_id, "pedido", titulo, detalle, pedido.id)


def avisar_pago(db: Session, pago, factura) -> None:
    if factura is not None:
        crear(db, factura.usuario_id, "pago", "Pago aprobado",
              f"Factura {factura.numero} · {_dinero(factura.total)}", pago.pedido_id)
        crear(db, factura.usuario_id, "calificacion", f"¿Cómo estuvo tu pedido #{pago.pedido_id}?",
              "Califica tus platos desde Mis pedidos.", pago.pedido_id)
    else:
        motivo = getattr(pago, "motivo_rechazo", None) or "La pasarela rechazó el pago"
        crear(db, getattr(pago, "usuario_id", None), "pago", "Pago rechazado",
              f"{motivo}. Puedes intentarlo de nuevo.", pago.pedido_id)


def avisar_factura_anulada(db: Session, factura, motivo: str) -> None:
    crear(db, factura.usuario_id, "pago", "Factura anulada",
          f"{factura.numero}: {motivo}", factura.pedido_id)


def avisar_reserva(db: Session, reserva, accion: str, motivo: Optional[str] = None) -> None:
    cuando = reserva.fecha_hora.strftime("%d/%m %I:%M %p") if reserva.fecha_hora else ""
    titulos = {
        "creada": "Reserva recibida",
        "modificada": "Reserva modificada",
        "cancelada": "Reserva cancelada",
    }
    crear(db, reserva.usuario_id, "reserva", titulos.get(accion, "Reserva actualizada"),
          f"Mesa {reserva.mesa.numero if reserva.mesa else reserva.mesa_id} · {cuando} · {reserva.numero_personas} personas"
          + (f" · Motivo: {motivo}" if motivo else ""),
          reserva.id)


# ───────────── Avisos al personal del restaurante (administrador + empleados) ─────────────
def avisar_personal(db: Session, restaurante_id: Optional[int], tipo: str, titulo: str,
                    detalle: Optional[str] = None, referencia_id: Optional[int] = None,
                    excluir_usuario_id: Optional[int] = None) -> None:
    """Crea la misma notificación para el administrador y los empleados de ese restaurante."""
    if restaurante_id is None:
        return
    try:
        from app.modules.auth.models import Restaurante, Usuario

        ids = set()
        rest = db.query(Restaurante).filter(Restaurante.id == restaurante_id).first()
        if rest and rest.administrador_id:
            ids.add(rest.administrador_id)
        for (uid,) in db.query(Usuario.id).filter(
            Usuario.restaurante_id == restaurante_id, Usuario.activo == True  # noqa: E712
        ).all():
            ids.add(uid)
        ids.discard(excluir_usuario_id)
        for uid in ids:
            crear(db, uid, tipo, titulo, detalle, referencia_id)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning("No se pudo avisar al personal (%s): %s", titulo, e)


def avisar_reserva_al_restaurante(db: Session, reserva, accion: str, motivo: Optional[str] = None,
                                  excluir_usuario_id: Optional[int] = None) -> None:
    rid = reserva.mesa.restaurante_id if reserva.mesa else None
    titulos = {"creada": "Nueva reserva", "modificada": "Reserva modificada",
               "cancelada": "Reserva cancelada por el cliente"}
    cuando = reserva.fecha_hora.strftime("%d/%m %I:%M %p") if reserva.fecha_hora else ""
    detalle = f"Mesa {reserva.mesa.numero} · {cuando} · {reserva.numero_personas} personas"
    if motivo:
        detalle += f" · Motivo: {motivo}"
    avisar_personal(db, rid, "reserva", titulos.get(accion, "Reserva actualizada"), detalle,
                    reserva.id, excluir_usuario_id)


def avisar_pedido_al_restaurante(db: Session, pedido) -> None:
    avisar_personal(db, pedido.restaurante_id, "pedido", f"Nuevo pedido #{pedido.id}",
                    f"{_lugar(pedido)} · {_dinero(pedido.total)}", pedido.id)


def avisar_pago_al_restaurante(db: Session, pedido_id: int, factura) -> None:
    from app.modules.pedidos.models import Pedido

    ped = db.query(Pedido).filter(Pedido.id == pedido_id).first()
    if ped is None:
        return
    avisar_personal(db, ped.restaurante_id, "pago", f"Pago recibido · pedido #{pedido_id}",
                    f"{factura.numero} · {_dinero(factura.total)}", pedido_id)


def avisar_resena_al_restaurante(db: Session, pedido_id: int) -> None:
    from sqlalchemy import func

    from app.modules.calificaciones.models import Calificacion

    filas = db.query(Calificacion).filter(Calificacion.pedido_id == pedido_id).all()
    if not filas:
        return
    prom = sum(f.estrellas for f in filas) / len(filas)
    coment = next((f.comentario for f in filas if f.comentario), None)
    detalle = f"Pedido #{pedido_id} · {prom:.1f}/5"
    if coment:
        detalle += f" · “{coment[:120]}”"
    avisar_personal(db, filas[0].restaurante_id, "calificacion", "Nueva reseña", detalle, pedido_id)
