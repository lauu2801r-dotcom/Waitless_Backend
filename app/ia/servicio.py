"""
WaitLess — Ciclo cerrado de la IA
==================================
1) Al CREAR un pedido  → se estima el tiempo y se guarda en el pedido y en `predicciones`.
2) Al quedar LISTO     → se anota el tiempo REAL y se compara con lo estimado.
3) Cada cierto número de pedidos reales nuevos → se reentrena solo.

Todo es "best effort": si algo falla, el pedido sigue su curso normal.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.ia.entrenamiento import (
    AUTO_REENTRENAR_CADA, hora_local, reentrenar_en_segundo_plano,
)
from app.ia.models import ModeloIA, Prediccion
from app.ia.prediccion import predecir_tiempo_espera
from app.modules.pedidos.models import EstadoPedido, Pedido

logger = logging.getLogger(__name__)


def _carga_actual(db: Session, restaurante_id, excluir_id: int) -> int:
    q = db.query(Pedido).filter(
        Pedido.id != excluir_id,
        Pedido.estado.in_([EstadoPedido.pendiente, EstadoPedido.en_preparacion]),
    )
    q = q.filter(Pedido.restaurante_id == restaurante_id) if restaurante_id is not None \
        else q.filter(Pedido.restaurante_id.is_(None))
    return q.count()


def estimar_al_crear(db: Session, pedido: Pedido) -> None:
    try:
        local = hora_local(pedido.creado_en)
        r = predecir_tiempo_espera(
            hora=local.hour, dia_semana=local.weekday(),
            mesas_ocupadas=_carga_actual(db, pedido.restaurante_id, pedido.id),
            total_items=sum(i.cantidad for i in pedido.items) or 1,
            total_pedido=float(pedido.total or 0),
            db=db, pedido_id=pedido.id, restaurante_id=pedido.restaurante_id,
        )
        pedido.minutos_estimados = r["minutos_estimados"]
        pedido.prediccion_id = r["id"]
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning("No se pudo estimar el pedido %s: %s", getattr(pedido, "id", "?"), e)


def cerrar_al_quedar_listo(db: Session, pedido: Pedido) -> None:
    """Anota el tiempo real en la predicción del pedido y revisa si toca reentrenar."""
    try:
        if pedido.listo_en is None or pedido.creado_en is None or not pedido.prediccion_id:
            return
        pred = db.query(Prediccion).filter(Prediccion.id == pedido.prediccion_id).first()
        if pred is None or pred.tiempo_real_minutos is not None:
            return
        pred.tiempo_real_minutos = round((pedido.listo_en - pedido.creado_en).total_seconds() / 60.0, 2)
        db.commit()
        _revisar_reentrenamiento(db)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning("No se pudo cerrar la predicción del pedido %s: %s", getattr(pedido, "id", "?"), e)


def _revisar_reentrenamiento(db: Session) -> None:
    ultimo = db.query(ModeloIA).order_by(ModeloIA.version.desc()).first()
    q = db.query(Pedido).filter(Pedido.listo_en.isnot(None))
    if ultimo is not None and ultimo.entrenado_en is not None:
        q = q.filter(Pedido.listo_en > ultimo.entrenado_en)
    if q.count() >= AUTO_REENTRENAR_CADA:
        logger.info("Hay %s pedidos reales nuevos: reentrenando el modelo", AUTO_REENTRENAR_CADA)
        reentrenar_en_segundo_plano()
