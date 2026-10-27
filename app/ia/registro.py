"""
WaitLess — Registro de versiones del modelo
============================================
Guarda en memoria el modelo ACTIVO (para no leer la BD en cada predicción) y
sabe cargarlo desde la tabla `modelos_ia`. Si todavía no existe ninguna versión,
entrena la primera sola ("arranque") para que el sistema nunca se quede sin modelo.
"""
import logging
import pickle
import threading
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.ia.models import ModeloIA

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cache: dict = {"modelo": None, "version": None, "id": None}


def invalidar() -> None:
    with _lock:
        _cache.update(modelo=None, version=None, id=None)
    logger.info("Cache del modelo invalidado")


def _activo_en_bd(db: Session) -> Optional[ModeloIA]:
    return (
        db.query(ModeloIA)
        .filter(ModeloIA.activo.is_(True), ModeloIA.archivo.isnot(None))
        .order_by(ModeloIA.version.desc())
        .first()
    )


def hay_modelo(db: Optional[Session] = None) -> bool:
    if _cache["modelo"] is not None:
        return True
    propia = db is None
    db = db or SessionLocal()
    try:
        return _activo_en_bd(db) is not None
    finally:
        if propia:
            db.close()


def obtener_modelo(db: Optional[Session] = None) -> Tuple[object, int]:
    """Devuelve (pipeline, número de versión). Lanza RuntimeError si no hay ninguno."""
    with _lock:
        if _cache["modelo"] is not None:
            return _cache["modelo"], _cache["version"]

    propia = db is None
    db = db or SessionLocal()
    try:
        fila = _activo_en_bd(db)
        if fila is None:
            # Primera vez: se entrena la versión de arranque (import aquí para evitar ciclos)
            from app.ia.entrenamiento import entrenar_modelo
            entrenar_modelo(db, motivo="arranque")
            fila = _activo_en_bd(db)
        if fila is None:
            raise RuntimeError("El modelo de IA aún no ha sido entrenado (POST /ia/entrenar).")
        modelo, version, mid = pickle.loads(fila.archivo), fila.version, fila.id
    finally:
        if propia:
            db.close()

    with _lock:
        _cache.update(modelo=modelo, version=version, id=mid)
    logger.info("Modelo cargado: versión %s", version)
    return modelo, version


def version_en_memoria() -> Optional[int]:
    return _cache["version"]
