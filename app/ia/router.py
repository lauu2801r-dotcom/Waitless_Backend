"""
WaitLess — Router del Módulo de IA
====================================
Expone los endpoints REST para entrenamiento, predicción y métricas del modelo.

Endpoints:
  POST /ia/entrenar          → Entrena (o re-entrena) el modelo
  GET  /ia/predecir          → Predice tiempo de espera para un pedido nuevo
  GET  /ia/afluencia         → Curva de ocupación por hora para un día
  GET  /ia/metricas          → Métricas de precisión del modelo en producción
  GET  /ia/ocupacion-hoy     → Resumen de ocupación del día actual
  GET  /ia/estado            → Estado general del modelo (existe, en cache, etc.)
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.ia.entrenamiento import entrenar_modelo, modelo_existe
from app.ia.prediccion import (
    predecir_tiempo_espera,
    predecir_afluencia_hora,
    invalidar_cache,
    info_modelo,
)
from app.ia.metricas import calcular_metricas_modelo, resumen_ocupacion_hoy

router = APIRouter()


# ─────────────────────────────────────────────────────────────
#  ENTRENAMIENTO
# ─────────────────────────────────────────────────────────────

@router.post("/entrenar", summary="Entrenar o re-entrenar el modelo de IA")
def entrenar(db: Session = Depends(get_db)):
    """
    Lanza el proceso de entrenamiento usando los pedidos históricos de la BD.
    Si hay pocas muestras reales, complementa con datos sintéticos de arranque.

    Invalida el cache del modelo en memoria después de entrenar.

    **Retorna** métricas del entrenamiento (MAE, R², muestras usadas).
    """
    resultado = entrenar_modelo(db)
    invalidar_cache()   # forzar recarga del nuevo modelo
    return resultado


# ─────────────────────────────────────────────────────────────
#  PREDICCIÓN
# ─────────────────────────────────────────────────────────────

@router.get("/predecir", summary="Predecir tiempo de espera de un pedido")
def predecir(
    hora: int = Query(..., ge=0, le=23, description="Hora del día (0-23)"),
    dia_semana: int = Query(..., ge=0, le=6, description="Día (0=lunes, 6=domingo)"),
    mesas_ocupadas: int = Query(..., ge=0, description="Mesas ocupadas actualmente"),
    total_items: int = Query(..., ge=1, description="Cantidad total de ítems en el pedido"),
    total_pedido: float = Query(..., gt=0, description="Valor total del pedido en COP"),
):
    """
    Predice cuántos minutos tardará el pedido en estar listo.

    Retorna el tiempo estimado, el rango de confianza (±20%),
    el nivel de ocupación actual y una recomendación para el cliente.
    """
    return predecir_tiempo_espera(
        hora=hora,
        dia_semana=dia_semana,
        mesas_ocupadas=mesas_ocupadas,
        total_items=total_items,
        total_pedido=total_pedido,
    )


@router.get("/afluencia", summary="Curva de ocupación por hora para un día de la semana")
def afluencia(
    dia_semana: int = Query(
        default=0, ge=0, le=6,
        description="Día de la semana (0=lunes … 6=domingo)"
    ),
):
    """
    Retorna una lista con la ocupación estimada (%) para cada hora del día
    (10:00 a 22:00). Se usa en la gráfica de barras del frontend.
    """
    return predecir_afluencia_hora(dia_semana=dia_semana)


# ─────────────────────────────────────────────────────────────
#  MÉTRICAS Y ESTADO
# ─────────────────────────────────────────────────────────────

@router.get("/metricas", summary="Métricas de precisión del modelo en producción")
def metricas(db: Session = Depends(get_db)):
    """
    Evalúa el modelo contra los pedidos reales de los últimos 30 días
    y retorna MAE, precisión dentro de ±5 y ±10 minutos, y distribución de errores.
    """
    return calcular_metricas_modelo(db)


@router.get("/ocupacion-hoy", summary="Estadísticas de ocupación del día actual")
def ocupacion_hoy(db: Session = Depends(get_db)):
    """
    Retorna pedidos agrupados por hora del día de hoy,
    con la hora pico y la hora más tranquila.
    """
    return resumen_ocupacion_hoy(db)


@router.get("/estado", summary="Estado del modelo de IA")
def estado():
    """
    Retorna si el modelo existe, si está cargado en cache y cuándo fue cargado.
    """
    return {
        **info_modelo(),
        "modelo_existe": modelo_existe(),
    }