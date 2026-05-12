"""
WaitLess — Módulo de Predicción
================================
Carga el modelo entrenado y expone funciones para predecir
el tiempo de espera de un pedido nuevo.

Uso desde el router:
    from app.ia.prediccion import predecir_tiempo_espera, info_modelo

    resultado = predecir_tiempo_espera(
        hora=14,
        dia_semana=4,          # viernes
        mesas_ocupadas=8,
        total_items=3,
        total_pedido=45000.0,
    )
"""

import os
import pickle
import logging
from datetime import datetime
from typing import Optional

import numpy as np

from app.ia.entrenamiento import MODEL_PATH, modelo_existe, entrenar_modelo

logger = logging.getLogger(__name__)

# Cache en memoria para no leer el .pkl en cada request
_modelo_cache = None
_cache_cargado_en: Optional[datetime] = None


# ─────────────────────────────────────────────────────────────
#  CARGA DEL MODELO
# ─────────────────────────────────────────────────────────────

def _cargar_modelo():
    """
    Carga el modelo desde disco (con cache en memoria).
    Si no existe, lanza RuntimeError.
    """
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
    """Fuerza la recarga del modelo (útil después de re-entrenar)."""
    global _modelo_cache, _cache_cargado_en
    _modelo_cache = None
    _cache_cargado_en = None
    logger.info("🗑️ Cache del modelo invalidado")


# ─────────────────────────────────────────────────────────────
#  PREDICCIÓN
# ─────────────────────────────────────────────────────────────

def predecir_tiempo_espera(
    hora: int,
    dia_semana: int,
    mesas_ocupadas: int,
    total_items: int,
    total_pedido: float,
) -> dict:
    """
    Predice el tiempo de espera estimado en minutos para un pedido nuevo.

    Parámetros:
        hora            : hora del día (0-23)
        dia_semana      : 0=lunes … 6=domingo
        mesas_ocupadas  : número de mesas actualmente ocupadas
        total_items     : cantidad total de ítems en el pedido
        total_pedido    : valor monetario total del pedido (COP)

    Retorna un dict con:
        {
          "minutos_estimados": int,       # tiempo predicho redondeado
          "rango_min": int,               # intervalo inferior (±20%)
          "rango_max": int,               # intervalo superior (±20%)
          "nivel_ocupacion": str,         # "bajo" | "medio" | "alto"
          "recomendacion": str,           # mensaje al cliente
          "hora_consulta": str,           # timestamp ISO
        }
    """
    modelo = _cargar_modelo()

    features = np.array([[hora, dia_semana, mesas_ocupadas, total_items, total_pedido]])
    prediccion_raw = float(modelo.predict(features)[0])

    # Aseguramos que esté en rango razonable (3 - 90 min)
    minutos = round(max(3.0, min(prediccion_raw, 90.0)))

    # Intervalo de confianza aproximado (±20%)
    margen = max(2, round(minutos * 0.20))
    rango_min = max(1, minutos - margen)
    rango_max = minutos + margen

    # Nivel de ocupación para UI
    if mesas_ocupadas <= 4:
        nivel = "bajo"
    elif mesas_ocupadas <= 9:
        nivel = "medio"
    else:
        nivel = "alto"

    # Mensaje contextualizado
    if minutos <= 10:
        recomendacion = "🟢 Tu pedido estará listo muy pronto."
    elif minutos <= 20:
        recomendacion = "🟡 Tiempo de espera normal. ¡Gracias por tu paciencia!"
    else:
        recomendacion = "🔴 Alta demanda en este momento. Te avisaremos cuando esté listo."

    return {
        "minutos_estimados": minutos,
        "rango_min": rango_min,
        "rango_max": rango_max,
        "nivel_ocupacion": nivel,
        "recomendacion": recomendacion,
        "hora_consulta": datetime.now().isoformat(),
    }


def predecir_afluencia_hora(dia_semana: int) -> list[dict]:
    """
    Predice el porcentaje de ocupación estimado por hora del día
    para un día de la semana dado. Útil para la gráfica de barras
    en las pantallas de predicción del frontend.

    Retorna una lista de 13 dicts (horas 10:00 a 22:00):
        [
          {"hora": "10:00", "hora_label": "10am", "ocupacion_pct": 35, "es_pico": False},
          ...
        ]
    """
    modelo = _cargar_modelo()

    # Parámetros fijos representativos para cada hora
    horas = list(range(10, 23))           # 10am a 10pm
    mesas_promedio = 7                     # ocupación media típica
    items_promedio = 3
    total_promedio = 45_000.0

    # Predecimos para cada hora (más mesas en horas pico)
    resultados = []
    for h in horas:
        # Simulamos más mesas ocupadas en horas pico
        if 12 <= h <= 14 or 19 <= h <= 21:
            mesas = 11
        elif 15 <= h <= 18:
            mesas = 6
        else:
            mesas = 3

        features = np.array([[h, dia_semana, mesas, items_promedio, total_promedio]])
        tiempo_pred = float(modelo.predict(features)[0])

        # Convertimos tiempo predicho a % de ocupación (escala inversa:
        # más tiempo de espera → más ocupación)
        # Normalizado: 3 min = 5%, 30 min = 85%, 60 min = 100%
        ocupacion = round(min(100, max(5, (tiempo_pred / 35.0) * 80 + 5)))

        # Etiqueta legible
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
#  INFO DEL MODELO
# ─────────────────────────────────────────────────────────────

def info_modelo() -> dict:
    """
    Retorna metadatos del modelo cargado actualmente.
    """
    existe = modelo_existe()
    if not existe:
        return {
            "modelo_disponible": False,
            "mensaje": "El modelo aún no ha sido entrenado.",
        }

    # Tamaño del archivo .pkl
    size_kb = round(os.path.getsize(MODEL_PATH) / 1024, 1)

    return {
        "modelo_disponible": True,
        "ruta": MODEL_PATH,
        "tamano_kb": size_kb,
        "cache_activo": _modelo_cache is not None,
        "cache_cargado_en": _cache_cargado_en.isoformat() if _cache_cargado_en else None,
    }