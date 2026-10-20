"""
WaitLess — Router del Módulo de IA
====================================
  POST /ia/entrenar     → Re-entrena el modelo           (solo administrador)
  GET  /ia/predecir     → Predice tiempo de espera       (usuario autenticado)
  GET  /ia/afluencia    → Curva de ocupación por hora    (usuario autenticado)
  GET  /ia/metricas     → Métricas de precisión          (solo administrador)
  GET  /ia/estado       → Estado del modelo              (público)
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, solo_admin
from app.ia.entrenamiento import entrenar_modelo, modelo_existe
from app.ia.metricas import calcular_metricas_modelo
from app.ia.prediccion import (
    info_modelo,
    predecir_afluencia_hora,
    predecir_tiempo_espera,
)

router = APIRouter()


@router.post("/entrenar")
def entrenar(
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    return entrenar_modelo(db)


@router.get("/predecir")
def predecir(
    hora: int = Query(..., ge=0, le=23),
    dia_semana: int = Query(..., ge=0, le=6),
    mesas_ocupadas: int = Query(..., ge=0),
    total_items: int = Query(..., ge=1),
    total_pedido: float = Query(..., gt=0),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if not modelo_existe():
        entrenar_modelo(db)
    return predecir_tiempo_espera(
        hora=hora,
        dia_semana=dia_semana,
        mesas_ocupadas=mesas_ocupadas,
        total_items=total_items,
        total_pedido=total_pedido,
        db=db,
    )


@router.get("/afluencia")
def afluencia(
    dia_semana: int = Query(..., ge=0, le=6),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if not modelo_existe():
        entrenar_modelo(db)
    return predecir_afluencia_hora(dia_semana=dia_semana)


@router.get("/metricas")
def metricas(
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    return calcular_metricas_modelo(db)


@router.get("/estado")
def estado():
    return {
        **info_modelo(),
        "modelo_existe": modelo_existe(),
    }
