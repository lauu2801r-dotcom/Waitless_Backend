"""
WaitLess — Módulo de Entrenamiento del Modelo de IA
====================================================
Entrena un modelo de Random Forest para predecir el tiempo de espera
basándose en los datos históricos de pedidos almacenados en la BD.

Features usadas para el modelo:
  - hora_del_dia      : hora en que llega el pedido (0-23)
  - dia_semana        : día de la semana (0=lunes … 6=domingo)
  - mesas_ocupadas    : cuántas mesas estaban ocupadas en ese momento
  - total_items       : cantidad total de ítems en el pedido
  - total_pedido      : valor monetario del pedido

Target (lo que predice):
  - tiempo_espera     : minutos desde que el pedido fue creado
                        hasta que pasó a estado "listo" o "entregado"
"""

import os
import pickle
import logging
from datetime import datetime
from typing import Optional

import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.modules.pedidos.models import Pedido, ItemPedido, EstadoPedido
from app.modules.mesas.models import Mesa, EstadoMesa

# ── Scikit-learn ──────────────────────────────────────────────
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.pipeline import Pipeline

logger = logging.getLogger(__name__)

# Ruta donde se guarda el modelo entrenado
MODEL_PATH = os.path.join(os.path.dirname(__file__), "modelo_waitless.pkl")

# Mínimo de muestras para entrenar (si hay menos, usamos datos sintéticos de apoyo)
MIN_MUESTRAS = 20


# ─────────────────────────────────────────────────────────────
#  EXTRACCIÓN DE DATOS
# ─────────────────────────────────────────────────────────────

def _extraer_dataset(db: Session) -> tuple[list[list], list[float]]:
    """
    Consulta los pedidos completados (entregados/listos) y construye
    la matriz de features X y el vector de tiempos de espera y.

    Retorna (X, y) donde cada fila de X corresponde a un pedido y
    y[i] es el tiempo en minutos que tardó ese pedido.
    """
    # Solo pedidos que ya terminaron (tenemos tiempo real)
    pedidos_completados = (
        db.query(Pedido)
        .filter(
            Pedido.estado.in_([EstadoPedido.entregado, EstadoPedido.listo]),
            Pedido.actualizado_en.isnot(None),
        )
        .all()
    )

    X: list[list] = []
    y: list[float] = []

    for pedido in pedidos_completados:
        # Tiempo de espera real en minutos
        tiempo_espera = (
            pedido.actualizado_en - pedido.creado_en
        ).total_seconds() / 60.0

        # Filtrar valores absurdos (< 1 min o > 3 horas)
        if not (1 <= tiempo_espera <= 180):
            continue

        # Features del pedido
        hora = pedido.creado_en.hour
        dia_semana = pedido.creado_en.weekday()
        total_items = sum(item.cantidad for item in pedido.items)

        # Mesas ocupadas en la hora de creación del pedido
        # (aproximación: contamos pedidos activos en ese instante)
        mesas_ocupadas = (
            db.query(func.count(Pedido.id))
            .filter(
                Pedido.creado_en <= pedido.creado_en,
                Pedido.actualizado_en >= pedido.creado_en,
                Pedido.estado != EstadoPedido.cancelado,
            )
            .scalar()
            or 0
        )

        X.append([hora, dia_semana, mesas_ocupadas, total_items, pedido.total])
        y.append(round(tiempo_espera, 2))

    return X, y


def _datos_sinteticos(n: int = 200) -> tuple[list[list], list[float]]:
    """
    Genera datos sintéticos realistas para el arranque del sistema
    cuando todavía hay pocas muestras reales.

    Lógica de negocio embebida:
      - Horas pico (12-14h, 19-21h) → más demora
      - Fines de semana → más concurrencia
      - Más ítems → más tiempo
    """
    rng = np.random.default_rng(seed=42)
    X: list[list] = []
    y: list[float] = []

    for _ in range(n):
        hora = int(rng.integers(10, 23))
        dia = int(rng.integers(0, 7))
        mesas = int(rng.integers(0, 15))
        items = int(rng.integers(1, 10))
        total = round(float(rng.uniform(15_000, 120_000)), 2)

        # Base: 8 minutos
        tiempo = 8.0
        # Hora pico almuerzo / cena
        if 12 <= hora <= 14 or 19 <= hora <= 21:
            tiempo += rng.uniform(4, 10)
        # Fin de semana
        if dia >= 5:
            tiempo += rng.uniform(2, 6)
        # Concurrencia
        tiempo += mesas * 0.4
        # Ítems
        tiempo += items * 1.2
        # Ruido
        tiempo += rng.normal(0, 1.5)
        tiempo = max(3.0, min(tiempo, 60.0))

        X.append([hora, dia, mesas, items, total])
        y.append(round(tiempo, 2))

    return X, y


# ─────────────────────────────────────────────────────────────
#  ENTRENAMIENTO
# ─────────────────────────────────────────────────────────────

def entrenar_modelo(db: Session) -> dict:
    """
    Entrena (o re-entrena) el modelo de predicción y lo guarda en disco.

    Retorna un dict con métricas del entrenamiento:
      {
        "muestras_reales": int,
        "muestras_sinteticas": int,
        "total_muestras": int,
        "mae_minutos": float,     # Error absoluto medio en minutos
        "r2_score": float,        # Qué tan bien explica la varianza (0-1)
        "modelo_guardado": bool,
      }
    """
    logger.info("🧠 Iniciando entrenamiento del modelo WaitLess…")

    X_real, y_real = _extraer_dataset(db)
    muestras_reales = len(X_real)
    muestras_sinteticas = 0

    # Si hay pocas muestras reales, complementamos con sintéticas
    if muestras_reales < MIN_MUESTRAS:
        logger.warning(
            f"Solo {muestras_reales} muestras reales. "
            f"Complementando con datos sintéticos de arranque."
        )
        X_sint, y_sint = _datos_sinteticos(n=max(200, MIN_MUESTRAS * 5))
        muestras_sinteticas = len(X_sint)
        X_all = X_real + X_sint
        y_all = y_real + y_sint
    else:
        X_all = X_real
        y_all = y_real

    X_arr = np.array(X_all)
    y_arr = np.array(y_all)

    # Split entrenamiento / validación
    if len(X_arr) >= 40:
        X_train, X_test, y_train, y_test = train_test_split(
            X_arr, y_arr, test_size=0.2, random_state=42
        )
    else:
        # Con pocas muestras, entrenamos con todo
        X_train, X_test, y_train, y_test = X_arr, X_arr, y_arr, y_arr

    # Pipeline: escalado + Random Forest
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("rf", RandomForestRegressor(
            n_estimators=100,
            max_depth=8,
            min_samples_leaf=3,
            random_state=42,
            n_jobs=-1,
        )),
    ])

    pipeline.fit(X_train, y_train)

    # Métricas en el set de validación
    y_pred = pipeline.predict(X_test)
    mae = round(float(mean_absolute_error(y_test, y_pred)), 2)
    r2 = round(float(r2_score(y_test, y_pred)), 4)

    # Guardar modelo en disco
    modelo_guardado = False
    try:
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(pipeline, f)
        modelo_guardado = True
        logger.info(f"✅ Modelo guardado en {MODEL_PATH}")
    except Exception as e:
        logger.error(f"❌ No se pudo guardar el modelo: {e}")

    resultado = {
        "muestras_reales": muestras_reales,
        "muestras_sinteticas": muestras_sinteticas,
        "total_muestras": len(X_all),
        "mae_minutos": mae,
        "r2_score": r2,
        "modelo_guardado": modelo_guardado,
        "entrenado_en": datetime.now().isoformat(),
    }

    logger.info(f"📊 Métricas → MAE: {mae} min | R²: {r2}")
    return resultado


def modelo_existe() -> bool:
    """Verifica si ya existe un modelo entrenado en disco."""
    return os.path.exists(MODEL_PATH)