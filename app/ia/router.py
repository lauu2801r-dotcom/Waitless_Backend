"""
WaitLess — Router del Módulo de IA (con persistencia en BD)
============================================================
Endpoints:
  POST /ia/entrenar              → Entrena o re-entrena el modelo
  GET  /ia/predecir              → Predice y GUARDA en BD
  GET  /ia/afluencia             → Curva de ocupación por hora
  GET  /ia/historial             → Lista predicciones guardadas en BD
  PATCH /ia/historial/{id}/real  → Registra el tiempo real de un pedido
  GET  /ia/metricas              → Métricas de precisión del modelo
  GET  /ia/ocupacion-hoy         → Resumen de ocupación del día
  GET  /ia/estado                → Estado del modelo
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.ia.entrenamiento import entrenar_modelo, modelo_existe
from app.ia.prediccion import (
    predecir_tiempo_espera,
    predecir_afluencia_hora,
    obtener_historial,
    registrar_tiempo_real,
    invalidar_cache,
    info_modelo,
)
from app.ia.metricas import calcular_metricas_modelo, resumen_ocupacion_hoy

router = APIRouter()


# ─────────────────────────────────────────────────────────────
#  SCHEMA
# ─────────────────────────────────────────────────────────────

class TiempoRealRequest(BaseModel):
    tiempo_real_minutos: float


# ─────────────────────────────────────────────────────────────
#  ENTRENAMIENTO
# ─────────────────────────────────────────────────────────────

@router.post("/entrenar", summary="Entrenar o re-entrenar el modelo de IA")
def entrenar(db: Session = Depends(get_db)):
    resultado = entrenar_modelo(db)
    invalidar_cache()
    return resultado


# ─────────────────────────────────────────────────────────────
#  PREDICCIÓN
# ─────────────────────────────────────────────────────────────

@router.get("/predecir", summary="Predecir tiempo de espera (se guarda en BD)")
def predecir(
    hora: int = Query(..., ge=0, le=23),
    dia_semana: int = Query(..., ge=0, le=6),
    mesas_ocupadas: int = Query(..., ge=0),
    total_items: int = Query(..., ge=1),
    total_pedido: float = Query(..., gt=0),
    pedido_id: int = Query(default=None, description="ID del pedido relacionado (opcional)"),
    db: Session = Depends(get_db),
):
    """
    Predice el tiempo de espera y guarda el resultado en la tabla `predicciones`.
    Retorna el `id` del registro guardado además del resultado.
    """
    return predecir_tiempo_espera(
        hora=hora,
        dia_semana=dia_semana,
        mesas_ocupadas=mesas_ocupadas,
        total_items=total_items,
        total_pedido=total_pedido,
        db=db,
        pedido_id=pedido_id,
    )


@router.get("/afluencia", summary="Curva de ocupación por hora para un día")
def afluencia(
    dia_semana: int = Query(default=0, ge=0, le=6),
):
    return predecir_afluencia_hora(dia_semana=dia_semana)


# ─────────────────────────────────────────────────────────────
#  HISTORIAL EN BD
# ─────────────────────────────────────────────────────────────

@router.get("/historial", summary="Ver predicciones guardadas en la BD")
def historial(
    limite: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """
    Retorna las últimas predicciones almacenadas en la tabla `predicciones`.
    Incluye el tiempo real si ya fue registrado.
    """
    return obtener_historial(db=db, limite=limite)


@router.patch(
    "/historial/{prediccion_id}/real",
    summary="Registrar el tiempo real que tardó un pedido",
)
def registrar_real(
    prediccion_id: int,
    body: TiempoRealRequest,
    db: Session = Depends(get_db),
):
    """
    Una vez que el pedido fue entregado, registra cuánto tardó realmente.
    Esto permite calcular la precisión del modelo con datos reales.
    """
    try:
        return registrar_tiempo_real(
            db=db,
            prediccion_id=prediccion_id,
            tiempo_real_minutos=body.tiempo_real_minutos,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─────────────────────────────────────────────────────────────
#  MÉTRICAS Y ESTADO
# ─────────────────────────────────────────────────────────────

@router.get("/metricas", summary="Métricas de precisión del modelo")
def metricas(db: Session = Depends(get_db)):
    return calcular_metricas_modelo(db)


@router.get("/ocupacion-hoy", summary="Estadísticas de ocupación del día actual")
def ocupacion_hoy(db: Session = Depends(get_db)):
    return resumen_ocupacion_hoy(db)


@router.get("/estado", summary="Estado del modelo de IA")
def estado():
    return {
        **info_modelo(),
        "modelo_existe": modelo_existe(),
    }