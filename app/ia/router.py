"""
WaitLess — Router del Módulo de IA
====================================
Endpoints:
  POST /ia/entrenar     → Entrena o re-entrena el modelo
  GET  /ia/predecir     → Predice tiempo de espera
  GET  /ia/afluencia    → Curva de ocupación por hora
  GET  /ia/metricas     → Métricas de precisión del modelo
  GET  /ia/estado       → Estado del modelo
"""

from fastapi import APIRouter, Depends, Header, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.core.security import verify_token
from app.ia.entrenamiento import entrenar_modelo, modelo_existe
from app.ia.prediccion import predecir_tiempo_espera, predecir_afluencia_hora, info_modelo
from app.ia.metricas import calcular_metricas_modelo

router = APIRouter()


def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token requerido"
        )
    token = authorization.split(" ")[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado"
        )
    return payload


@router.post("/entrenar")
def entrenar(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
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
    current_user: dict = Depends(get_current_user)
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
    current_user: dict = Depends(get_current_user)
):
    if not modelo_existe():
        entrenar_modelo(db)
    return predecir_afluencia_hora(dia_semana=dia_semana)


@router.get("/metricas")
def metricas(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return calcular_metricas_modelo(db)


@router.get("/estado")
def estado():
    return {
        **info_modelo(),
        "modelo_existe": modelo_existe(),
    }