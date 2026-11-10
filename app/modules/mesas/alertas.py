"""
HU-004 — Alerta de mesa ocupada demasiado tiempo.

Cada minuto se revisan las mesas ocupadas. Si una supera el tiempo máximo del
restaurante (por defecto 90 min, configurable de 15 a 480), se avisa UNA vez al
personal por mesa y ocupación, y se marca la mesa para mostrarla en rojo.
"""
import asyncio
import logging
from datetime import datetime

from app.core.database import SessionLocal
from app.modules.mesas.models import EstadoMesa, Mesa

logger = logging.getLogger("waitless.mesas.alertas")
MINUTOS_POR_DEFECTO = 90
CADA_SEGUNDOS = 60


def revisar(db) -> int:
    """Revisa las mesas ocupadas y avisa de las que se pasaron. Devuelve cuántas alertas nuevas se enviaron."""
    from app.modules.auth.models import Restaurante
    from app.modules.notificaciones import service as notificaciones
    from app.websocket.manager import manager

    ahora = datetime.utcnow()
    umbrales = {}
    nuevas = 0
    for m in db.query(Mesa).filter(Mesa.estado == EstadoMesa.ocupada, Mesa.activa == True).all():  # noqa: E712
        if m.ocupada_desde is None:     # ocupada desde antes de existir esta función: se empieza a contar ahora
            m.ocupada_desde = ahora
            continue
        if m.alerta_tiempo_enviada:
            continue
        if m.restaurante_id not in umbrales:
            r = db.query(Restaurante).filter(Restaurante.id == m.restaurante_id).first() if m.restaurante_id else None
            umbrales[m.restaurante_id] = (r.minutos_alerta_mesa if r and r.minutos_alerta_mesa else MINUTOS_POR_DEFECTO)
        limite = umbrales[m.restaurante_id]
        minutos = int((ahora - m.ocupada_desde).total_seconds() // 60)
        if minutos >= limite:
            m.alerta_tiempo_enviada = True
            db.commit()
            notificaciones.avisar_personal(
                db, m.restaurante_id, "mesa", f"Mesa {m.numero} lleva {minutos} min ocupada",
                f"Superó el tiempo máximo de {limite} min. Revisa si necesitan algo o si ya pueden liberarla.", m.id)
            manager.emitir("mesas", {"tipo": "mesa_alerta", "mesa_id": m.id, "numero": m.numero,
                                     "minutos": minutos, "mensaje": f"Mesa {m.numero} lleva {minutos} min ocupada"})
            manager.emitir("dashboard", {"tipo": "mesa_alerta", "mesa_id": m.id, "mensaje": f"Mesa {m.numero} lleva {minutos} min ocupada"})
            nuevas += 1
    db.commit()
    return nuevas


def _revisar_una_vez() -> int:
    db = SessionLocal()
    try:
        return revisar(db)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning("No se pudieron revisar las mesas: %s", e)
        return 0
    finally:
        db.close()


async def bucle() -> None:
    """Tarea de fondo: se inicia al arrancar la API."""
    while True:
        await asyncio.sleep(CADA_SEGUNDOS)
        await asyncio.to_thread(_revisar_una_vez)
