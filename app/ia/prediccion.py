"""
WaitLess — Módulo de Predicción (con persistencia en BD)
=========================================================
Carga el modelo entrenado, predice el tiempo de espera
y guarda cada consulta en la tabla `predicciones`.
"""

import os
import pickle
import logging
from datetime import datetime
from typing import Optional

import numpy as np
from sqlalchemy.orm import Session

from app.ia.entrenamiento import MODEL_PATH, modelo_existe, entrenar_modelo
from app.ia.models import Prediccion

logger = logging.getLogger(__name__)

_modelo_cache = None
_cache_cargado_en: Optional[datetime] = None


# ─────────────────────────────────────────────────────────────
#  CARGA DEL MODELO
# ─────────────────────────────────────────────────────────────

def _cargar_modelo():
    global _modelo_cache, _cache_cargado_en

    if _modelo_cache is not None:
        return _modelo_cache

    if not modelo_existe():
        raise RuntimeError(
            "El modelo de IA no ha sido entrenado aún. "
            "Llama primero a POST /ia/entrenar"
        )

    with open(MODEL_PATH, "rb") as f:
        _modelo_cache = pickle.load(f)

    _cache_cargado_en = datetime.now()
    logger.info(f"🔄 Modelo cargado desde {MODEL_PATH}")
    return _modelo_cache


def invalidar_cache():
    global _modelo_cache, _cache_cargado_en
    _modelo_cache = None
    _cache_cargado_en = None
    logger.info("🗑️ Cache del modelo invalidado")


# ─────────────────────────────────────────────────────────────
#  PREDICCIÓN (guarda en BD)
# ─────────────────────────────────────────────────────────────

def predecir_tiempo_espera(
    hora: int,
    dia_semana: int,
    mesas_ocupadas: int,
    total_items: int,
    total_pedido: float,
    db: Optional[Session] = None,          # ← recibe la sesión para guardar
    pedido_id: Optional[int] = None,        # ← referencia opcional al pedido
) -> dict:
    """
    Predice el tiempo de espera y guarda el resultado en la BD.

    Retorna:
        {
          "id": int,                        ← ID del registro guardado en BD
          "minutos_estimados": int,
          "rango_min": int,
          "rango_max": int,
          "nivel_ocupacion": str,
          "recomendacion": str,
          "hora_consulta": str,
        }
    """
    modelo = _cargar_modelo()

    features = np.array([[hora, dia_semana, mesas_ocupadas, total_items, total_pedido]])
    prediccion_raw = float(modelo.predict(features)[0])
    minutos = round(max(3.0, min(prediccion_raw, 90.0)))

    margen = max(2, round(minutos * 0.20))
    rango_min = max(1, minutos - margen)
    rango_max = minutos + margen

    if mesas_ocupadas <= 4:
        nivel = "bajo"
    elif mesas_ocupadas <= 9:
        nivel = "medio"
    else:
        nivel = "alto"

    if minutos <= 10:
        recomendacion = "🟢 Tu pedido estará listo muy pronto."
    elif minutos <= 20:
        recomendacion = "🟡 Tiempo de espera normal. ¡Gracias por tu paciencia!"
    else:
        recomendacion = "🔴 Alta demanda en este momento. Te avisaremos cuando esté listo."

    # ── Guardar en BD ────────────────────────────────────────
    prediccion_id = None
    if db is not None:
        try:
            registro = Prediccion(
                hora=hora,
                dia_semana=dia_semana,
                mesas_ocupadas=mesas_ocupadas,
                total_items=total_items,
                total_pedido=total_pedido,
                minutos_estimados=minutos,
                rango_min=rango_min,
                rango_max=rango_max,
                nivel_ocupacion=nivel,
                recomendacion=recomendacion,
                pedido_id=pedido_id,
            )
            db.add(registro)
            db.commit()
            db.refresh(registro)
            prediccion_id = registro.id
            logger.info(f"💾 Predicción guardada en BD con id={prediccion_id}")
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Error guardando predicción en BD: {e}")

    return {
        "id": prediccion_id,
        "minutos_estimados": minutos,
        "rango_min": rango_min,
        "rango_max": rango_max,
        "nivel_ocupacion": nivel,
        "recomendacion": recomendacion,
        "hora_consulta": datetime.now().isoformat(),
    }


def predecir_afluencia_hora(dia_semana: int) -> list[dict]:
    """
    Curva de ocupación estimada por hora del día.
    No guarda en BD porque es una consulta analítica, no una predicción real.
    """
    modelo = _cargar_modelo()
    horas = list(range(10, 23))
    items_promedio = 3
    total_promedio = 45_000.0

    resultados = []
    for h in horas:
        if 12 <= h <= 14 or 19 <= h <= 21:
            mesas = 11
        elif 15 <= h <= 18:
            mesas = 6
        else:
            mesas = 3

        features = np.array([[h, dia_semana, mesas, items_promedio, total_promedio]])
        tiempo_pred = float(modelo.predict(features)[0])
        ocupacion = round(min(100, max(5, (tiempo_pred / 35.0) * 80 + 5)))

        sufijo = "am" if h < 12 else "pm"
        h12 = h if h <= 12 else h - 12
        hora_label = f"{h12}{sufijo}"

        resultados.append({
            "hora": f"{h:02d}:00",
            "hora_label": hora_label,
            "ocupacion_pct": ocupacion,
            "es_pico": ocupacion >= 75,
        })

    return resultados


# ─────────────────────────────────────────────────────────────
#  HISTORIAL DE PREDICCIONES
# ─────────────────────────────────────────────────────────────

def obtener_historial(db: Session, limite: int = 50) -> list[dict]:
    """
    Retorna las últimas `limite` predicciones guardadas en la BD.
    Útil para la pantalla admin.
    """
    registros = (
        db.query(Prediccion)
        .order_by(Prediccion.creado_en.desc())
        .limit(limite)
        .all()
    )

    return [
        {
            "id": r.id,
            "hora": r.hora,
            "dia_semana": r.dia_semana,
            "mesas_ocupadas": r.mesas_ocupadas,
            "total_items": r.total_items,
            "minutos_estimados": r.minutos_estimados,
            "rango_min": r.rango_min,
            "rango_max": r.rango_max,
            "nivel_ocupacion": r.nivel_ocupacion,
            "tiempo_real_minutos": r.tiempo_real_minutos,
            "pedido_id": r.pedido_id,
            "creado_en": r.creado_en.isoformat() if r.creado_en else None,
        }
        for r in registros
    ]


def registrar_tiempo_real(
    db: Session,
    prediccion_id: int,
    tiempo_real_minutos: float,
) -> dict:
    """
    Actualiza una predicción con el tiempo real que tardó el pedido.
    Permite calcular qué tan preciso fue el modelo.
    """
    registro = db.query(Prediccion).filter(Prediccion.id == prediccion_id).first()
    if not registro:
        raise ValueError(f"Predicción con id={prediccion_id} no encontrada")

    registro.tiempo_real_minutos = tiempo_real_minutos
    db.commit()
    db.refresh(registro)

    error = abs(registro.minutos_estimados - tiempo_real_minutos)
    return {
        "id": registro.id,
        "minutos_estimados": registro.minutos_estimados,
        "tiempo_real_minutos": tiempo_real_minutos,
        "error_minutos": round(error, 2),
        "actualizado": True,
    }


# ─────────────────────────────────────────────────────────────
#  INFO DEL MODELO
# ─────────────────────────────────────────────────────────────

def info_modelo() -> dict:
    existe = modelo_existe()
    if not existe:
        return {
            "modelo_disponible": False,
            "mensaje": "El modelo aún no ha sido entrenado.",
        }

    size_kb = round(os.path.getsize(MODEL_PATH) / 1024, 1)
    return {
        "modelo_disponible": True,
        "ruta": MODEL_PATH,
        "tamano_kb": size_kb,
        "cache_activo": _modelo_cache is not None,
        "cache_cargado_en": _cache_cargado_en.isoformat() if _cache_cargado_en else None,
    }