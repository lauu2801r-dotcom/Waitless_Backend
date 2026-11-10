from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import es_personal, restaurante_id_de
from app.modules.mesas.models import EstadoMesa, Mesa
from app.modules.restaurantes import horarios as horarios_mod
from app.modules.reservas.models import EstadoReserva, Reserva
from app.modules.reservas.schemas import ReservaActualizar, ReservaCrear

MOTIVO_MAX = 255
TOLERANCIA_MIN = 5  # margen para que "ahora mismo" no falle por segundos de diferencia


def _ahora_colombia() -> datetime:
    """Las horas de reserva se guardan como hora local de Colombia (UTC-5), sin zona."""
    return datetime.utcnow() - timedelta(hours=5)


def _validar_futura(fecha_hora: datetime) -> None:
    f = fecha_hora.replace(tzinfo=None) if fecha_hora.tzinfo else fecha_hora
    if f < _ahora_colombia() - timedelta(minutes=TOLERANCIA_MIN):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La fecha y hora de la reserva debe ser futura",
        )


def _validar_horario(db: Session, mesa: Optional[Mesa], fecha_hora: datetime) -> None:
    """HU-023: no se reserva en un día cerrado ni fuera del horario (si el restaurante lo configuró)."""
    if mesa is None or mesa.restaurante_id is None:
        return
    from app.modules.auth.models import Restaurante

    r = db.query(Restaurante).filter(Restaurante.id == mesa.restaurante_id).first()
    if r is None:
        return
    f = fecha_hora.replace(tzinfo=None) if fecha_hora.tzinfo else fecha_hora
    abierto, mensaje = horarios_mod.estado_en(r.horarios, f)
    if abierto is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=mensaje)


def _err(codigo: int, detalle: str) -> HTTPException:
    return HTTPException(status_code=codigo, detail=detalle)


def crear_reserva(db: Session, datos: ReservaCrear, usuario_id: int):
    mesa = db.query(Mesa).filter(Mesa.id == datos.mesa_id, Mesa.activa == True).first()  # noqa: E712
    if not mesa:
        raise _err(status.HTTP_404_NOT_FOUND, "Mesa no encontrada")
    if mesa.estado not in [EstadoMesa.libre]:
        raise _err(status.HTTP_400_BAD_REQUEST,
                   f"La mesa no está disponible. Estado actual: {mesa.estado.value if hasattr(mesa.estado, 'value') else mesa.estado}")
    if datos.numero_personas > mesa.capacidad:
        raise _err(status.HTTP_400_BAD_REQUEST,
                   f"La mesa tiene capacidad para {mesa.capacidad} personas")
    _validar_futura(datos.fecha_hora)
    _validar_horario(db, mesa, datos.fecha_hora)

    nueva = Reserva(
        usuario_id=usuario_id, mesa_id=datos.mesa_id, fecha_hora=datos.fecha_hora,
        numero_personas=datos.numero_personas, notas=datos.notas, tiempo_espera_estimado=15,
    )
    mesa.estado = EstadoMesa.reservada
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


def obtener_reservas(db: Session, usuario_id: int):
    return db.query(Reserva).filter(Reserva.usuario_id == usuario_id).order_by(Reserva.fecha_hora.desc()).all()


def obtener_todas_reservas(db: Session, restaurante_id: Optional[int] = None):
    """Todas las reservas; si el personal pertenece a un restaurante, solo las de ese restaurante."""
    q = db.query(Reserva)
    if restaurante_id is not None:
        q = q.join(Mesa, Mesa.id == Reserva.mesa_id).filter(Mesa.restaurante_id == restaurante_id)
    return q.order_by(Reserva.fecha_hora.desc()).all()


def obtener_reserva(db: Session, reserva_id: int):
    reserva = db.query(Reserva).filter(Reserva.id == reserva_id).first()
    if not reserva:
        raise _err(status.HTTP_404_NOT_FOUND, "Reserva no encontrada")
    return reserva


def puede_gestionar(db: Session, reserva: Reserva, current_user: dict) -> bool:
    """Dueño de la reserva, o personal del mismo restaurante de la mesa."""
    if reserva.usuario_id == int(current_user["sub"]):
        return True
    if not es_personal(current_user):
        return False
    rid = restaurante_id_de(db, current_user)
    mesa_rid = reserva.mesa.restaurante_id if reserva.mesa else None
    return rid is None or mesa_rid is None or rid == mesa_rid


def _liberar_mesa(reserva: Reserva) -> None:
    # Solo se libera si sigue "reservada": una mesa ya ocupada por clientes no se toca.
    if reserva.mesa and reserva.mesa.estado == EstadoMesa.reservada:
        reserva.mesa.estado = EstadoMesa.libre


def actualizar_reserva(db: Session, reserva_id: int, datos: ReservaActualizar, current_user: dict):
    reserva = obtener_reserva(db, reserva_id)
    if not puede_gestionar(db, reserva, current_user):
        raise _err(status.HTTP_403_FORBIDDEN, "No tienes permiso para modificar esta reserva")
    if reserva.estado in (EstadoReserva.cancelada, EstadoReserva.completada):
        raise _err(status.HTTP_400_BAD_REQUEST,
                   f"No se puede modificar una reserva {reserva.estado.value}")

    cambios = datos.model_dump(exclude_unset=True)
    personal = es_personal(current_user)

    if "estado" in cambios:
        if not personal:
            raise _err(status.HTTP_403_FORBIDDEN, "Solo el restaurante puede cambiar el estado de la reserva")
        nuevo = cambios.pop("estado")
        if nuevo == EstadoReserva.cancelada:
            raise _err(status.HTTP_400_BAD_REQUEST, "Para cancelar usa DELETE /reservas/{id} con el motivo")
        if nuevo is not None and nuevo != reserva.estado:
            reserva.estado = nuevo
            if nuevo == EstadoReserva.completada:
                _liberar_mesa(reserva)

    if cambios.get("fecha_hora") is not None:
        _validar_futura(cambios["fecha_hora"])
        _validar_horario(db, reserva.mesa, cambios["fecha_hora"])
    if cambios.get("numero_personas") is not None and reserva.mesa \
            and cambios["numero_personas"] > reserva.mesa.capacidad:
        raise _err(status.HTTP_400_BAD_REQUEST,
                   f"La mesa tiene capacidad para {reserva.mesa.capacidad} personas")

    for campo, valor in cambios.items():
        if valor is None and campo != "notas":
            continue
        setattr(reserva, campo, valor)

    db.commit()
    db.refresh(reserva)
    return reserva


def cancelar_reserva(db: Session, reserva_id: int, current_user: dict, motivo: Optional[str] = None):
    reserva = obtener_reserva(db, reserva_id)
    if not puede_gestionar(db, reserva, current_user):
        raise _err(status.HTTP_403_FORBIDDEN, "No tienes permiso para cancelar esta reserva")
    if reserva.estado == EstadoReserva.cancelada:
        raise _err(status.HTTP_400_BAD_REQUEST, "La reserva ya está cancelada")
    if reserva.estado == EstadoReserva.completada:
        raise _err(status.HTTP_400_BAD_REQUEST, "No se puede cancelar una reserva completada")

    motivo = (motivo or "").strip()[:MOTIVO_MAX] or None
    _liberar_mesa(reserva)
    reserva.estado = EstadoReserva.cancelada
    reserva.motivo_cancelacion = motivo
    db.commit()
    db.refresh(reserva)
    return reserva
