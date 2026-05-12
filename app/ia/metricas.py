"""
WaitLess — Módulo de Métricas del Modelo de IA
===============================================
Calcula y expone métricas de rendimiento del modelo entrenado,
usando los pedidos reales de la base de datos.

Estos datos se muestran en la pantalla AdminPrediccionScreen del frontend.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.modules.pedidos.models import Pedido, ItemPedido, EstadoPedido
from app.ia.prediccion import predecir_tiempo_espera, modelo_existe

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
#  MÉTRICAS EN PRODUCCIÓN
# ─────────────────────────────────────────────────────────────

def calcular_metricas_modelo(db: Session) -> dict:
    """
    Evalúa el modelo contra los últimos pedidos reales de la BD
    y calcula métricas de precisión en producción.

    Retorna:
        {
          "modelo_disponible": bool,
          "total_pedidos_evaluados": int,
          "mae_minutos": float,        # error promedio en minutos
          "precision_10min": float,    # % dentro de ±10 min del real
          "tiempo_promedio_real": float,
          "tiempo_promedio_predicho": float,
          "distribucion_errores": {...},
          "calculado_en": str,
        }
    """
    if not modelo_existe():
        return {
            "modelo_disponible": False,
            "mensaje": "El modelo aún no ha sido entrenado. Usa POST /ia/entrenar",
        }

    # Pedidos completados en los últimos 30 días
    hace_30_dias = datetime.now() - timedelta(days=30)
    pedidos = (
        db.query(Pedido)
        .filter(
            Pedido.estado.in_([EstadoPedido.entregado, EstadoPedido.listo]),
            Pedido.actualizado_en.isnot(None),
            Pedido.creado_en >= hace_30_dias,
        )
        .all()
    )

    if not pedidos:
        return {
            "modelo_disponible": True,
            "total_pedidos_evaluados": 0,
            "mensaje": "Sin pedidos completados en los últimos 30 días para evaluar.",
        }

    errores = []
    tiempos_reales = []
    tiempos_predichos = []

    # Mesas ocupadas actuales (proxy para evaluación)
    mesas_activas = (
        db.query(func.count(Pedido.id))
        .filter(Pedido.estado.in_([EstadoPedido.pendiente, EstadoPedido.en_preparacion]))
        .scalar()
        or 0
    )

    for pedido in pedidos:
        tiempo_real = (pedido.actualizado_en - pedido.creado_en).total_seconds() / 60.0
        if not (1 <= tiempo_real <= 180):
            continue

        total_items = sum(item.cantidad for item in pedido.items)

        try:
            resultado = predecir_tiempo_espera(
                hora=pedido.creado_en.hour,
                dia_semana=pedido.creado_en.weekday(),
                mesas_ocupadas=mesas_activas,
                total_items=total_items,
                total_pedido=pedido.total,
            )
            predicho = resultado["minutos_estimados"]
        except Exception:
            continue

        error = abs(tiempo_real - predicho)
        errores.append(error)
        tiempos_reales.append(tiempo_real)
        tiempos_predichos.append(predicho)

    if not errores:
        return {
            "modelo_disponible": True,
            "total_pedidos_evaluados": 0,
            "mensaje": "No se pudieron calcular métricas con los datos disponibles.",
        }

    n = len(errores)
    mae = round(sum(errores) / n, 2)
    precision_5 = round(sum(1 for e in errores if e <= 5) / n * 100, 1)
    precision_10 = round(sum(1 for e in errores if e <= 10) / n * 100, 1)
    prom_real = round(sum(tiempos_reales) / n, 2)
    prom_pred = round(sum(tiempos_predichos) / n, 2)

    # Distribución de errores en rangos
    distribucion = {
        "0_a_5_min": sum(1 for e in errores if e <= 5),
        "5_a_10_min": sum(1 for e in errores if 5 < e <= 10),
        "10_a_20_min": sum(1 for e in errores if 10 < e <= 20),
        "mas_de_20_min": sum(1 for e in errores if e > 20),
    }

    return {
        "modelo_disponible": True,
        "total_pedidos_evaluados": n,
        "mae_minutos": mae,
        "precision_5min_pct": precision_5,
        "precision_10min_pct": precision_10,
        "tiempo_promedio_real_min": prom_real,
        "tiempo_promedio_predicho_min": prom_pred,
        "distribucion_errores": distribucion,
        "calculado_en": datetime.now().isoformat(),
    }


def resumen_ocupacion_hoy(db: Session) -> dict:
    """
    Estadísticas de ocupación del día de hoy. Las usa el dashboard admin.

    Retorna:
        {
          "hora_pico": str,           # ej: "20:00"
          "hora_pico_pct": int,
          "hora_mas_tranquila": str,
          "hora_tranquila_pct": int,
          "pedidos_por_hora": [{"hora": "12:00", "pedidos": 5}, ...]
        }
    """
    hoy = datetime.now().date()

    # Pedidos agrupados por hora del día de hoy
    pedidos_hoy = (
        db.query(
            func.extract("hour", Pedido.creado_en).label("hora"),
            func.count(Pedido.id).label("total"),
        )
        .filter(
            func.date(Pedido.creado_en) == hoy,
            Pedido.estado != EstadoPedido.cancelado,
        )
        .group_by("hora")
        .order_by("hora")
        .all()
    )

    if not pedidos_hoy:
        return {
            "pedidos_por_hora": [],
            "hora_pico": None,
            "hora_pico_pedidos": 0,
            "hora_mas_tranquila": None,
        }

    pedidos_hora = [
        {"hora": f"{int(row.hora):02d}:00", "pedidos": int(row.total)}
        for row in pedidos_hoy
    ]

    hora_pico = max(pedidos_hora, key=lambda x: x["pedidos"])
    hora_tranquila = min(pedidos_hora, key=lambda x: x["pedidos"])

    return {
        "pedidos_por_hora": pedidos_hora,
        "hora_pico": hora_pico["hora"],
        "hora_pico_pedidos": hora_pico["pedidos"],
        "hora_mas_tranquila": hora_tranquila["hora"],
        "hora_tranquila_pedidos": hora_tranquila["pedidos"],
    }