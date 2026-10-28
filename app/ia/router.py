"""
WaitLess — Router del módulo de IA
===================================
  GET  /ia/estado                 Estado del modelo activo               (público)
  GET  /ia/predecir               Predice el tiempo de espera            (autenticado)
  GET  /ia/afluencia-semanal      Pedidos promedio por día de la semana  (autenticado)
  GET  /ia/contexto               Mesas y cocina del restaurante AHORA   (autenticado)
  GET  /ia/afluencia              Curva de afluencia por hora            (autenticado)
  GET  /ia/metricas               Métricas reales + alertas (filtros)    (administrador)
  GET  /ia/versiones              Versiones del modelo y su rendimiento  (administrador)
  POST /ia/entrenar               Entrena una versión nueva              (administrador)
  POST /ia/versiones/{id}/activar Activa una versión anterior            (administrador)
  GET  /ia/historial              Últimas predicciones                   (administrador)
  GET  /ia/exportar               Predicciones/métricas en CSV           (administrador)
"""
import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, restaurante_id_de, solo_admin
from app.ia.entrenamiento import activar_version, entrenar_modelo, modelo_existe
from app.ia.metricas import (
    UMBRAL_MAE_MIN, UMBRAL_PRECISION_MIN, calcular_metricas_modelo,
    filas_para_exportar, listar_versiones,
)
from app.ia.prediccion import (
    info_modelo, nivel_cocina, obtener_historial, predecir_afluencia_hora, predecir_afluencia_semana,
    predecir_tiempo_espera,
)
from app.ia.servicio import _carga_actual
from app.modules.mesas.models import EstadoMesa
from app.modules.mesas.service import obtener_mesas

router = APIRouter()


@router.get("/estado")
def estado(db: Session = Depends(get_db)):
    return {**info_modelo(db), "modelo_existe": modelo_existe(db)}


@router.post("/entrenar")
def entrenar(db: Session = Depends(get_db), current_user: dict = Depends(solo_admin)):
    """Entrena una versión nueva con los pedidos reales (y datos de arranque si faltan)."""
    return entrenar_modelo(db, motivo="manual")


@router.get("/predecir")
def predecir(
    hora: int = Query(..., ge=0, le=23),
    dia_semana: int = Query(..., ge=0, le=6),
    total_items: int = Query(..., ge=1),
    total_pedido: float = Query(..., gt=0),
    mesas_ocupadas: Optional[int] = Query(None, ge=0),
    restaurante_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Si NO se manda `mesas_ocupadas`, la carga se calcula sola con los pedidos que la
    cocina del restaurante tiene en curso (igual que al crear un pedido real).
    """
    if not modelo_existe(db):
        entrenar_modelo(db, motivo="arranque")
    rid = restaurante_id_de(db, current_user) or restaurante_id
    de_cocina = mesas_ocupadas is None
    carga = _carga_actual(db, rid, excluir_id=-1) if de_cocina else mesas_ocupadas
    return predecir_tiempo_espera(
        hora=hora, dia_semana=dia_semana, mesas_ocupadas=carga,
        total_items=total_items, total_pedido=total_pedido, db=db,
        restaurante_id=rid, carga_de_cocina=de_cocina, guardar=False,
    )


@router.get("/contexto")
def contexto(
    restaurante_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Cómo está el restaurante AHORA: mesas y pedidos en cocina (para la pantalla del cliente)."""
    rid = restaurante_id_de(db, current_user) or restaurante_id
    mesas = obtener_mesas(db, restaurante_id=rid)
    ocupadas = sum(1 for m in mesas if m.estado == EstadoMesa.ocupada)
    en_cocina = _carga_actual(db, rid, excluir_id=-1)
    return {
        "restaurante_id": rid,
        "mesas_totales": len(mesas),
        "mesas_ocupadas": ocupadas,
        "mesas_libres": len(mesas) - ocupadas,
        "pedidos_en_cocina": en_cocina,
        "nivel_cocina": nivel_cocina(en_cocina),
    }


@router.get("/afluencia")
def afluencia(
    dia_semana: int = Query(..., ge=0, le=6),
    restaurante_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if not modelo_existe(db):
        entrenar_modelo(db, motivo="arranque")
    rid = restaurante_id_de(db, current_user) or restaurante_id
    return predecir_afluencia_hora(dia_semana=dia_semana, db=db, restaurante_id=rid)


@router.get("/afluencia-semanal")
def afluencia_semanal(
    restaurante_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Qué días se llena más el restaurante (con sus pedidos reales)."""
    rid = restaurante_id_de(db, current_user) or restaurante_id
    return predecir_afluencia_semana(db, rid)


@router.get("/metricas")
def metricas(
    version: Optional[int] = None,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    umbral_mae: float = Query(UMBRAL_MAE_MIN, gt=0),
    umbral_precision: float = Query(UMBRAL_PRECISION_MIN, ge=0, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    """Métricas del modelo SOLO con los pedidos de tu restaurante."""
    return calcular_metricas_modelo(
        db, restaurante_id_de(db, current_user), version, desde, hasta, umbral_mae, umbral_precision)


@router.get("/versiones")
def versiones(db: Session = Depends(get_db), current_user: dict = Depends(solo_admin)):
    return listar_versiones(db)


@router.post("/versiones/{version_id}/activar")
def activar(version_id: int, db: Session = Depends(get_db), current_user: dict = Depends(solo_admin)):
    fila = activar_version(db, version_id)
    if fila is None:
        raise HTTPException(404, "Versión no encontrada")
    return {"version": fila.version, "activo": True}


@router.get("/historial")
def historial(
    limite: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    return obtener_historial(db, restaurante_id_de(db, current_user), limite)


@router.get("/exportar")
def exportar(
    version: Optional[int] = None,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    """CSV (abre en Excel) con cada predicción, su tiempo real y su error."""
    filas = filas_para_exportar(db, restaurante_id_de(db, current_user), version, desde, hasta)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "fecha_utc", "pedido_id", "version_modelo", "hora", "dia_semana", "carga",
                "items", "total_pedido", "minutos_estimados", "rango_min", "rango_max",
                "confianza", "nivel", "tiempo_real_min", "error_min"])
    for f in filas:
        real = f.tiempo_real_minutos
        w.writerow([
            f.id, f.creado_en.isoformat() if f.creado_en else "", f.pedido_id or "",
            f.version_modelo if f.version_modelo is not None else "", f.hora, f.dia_semana,
            f.mesas_ocupadas, f.total_items, f.total_pedido, f.minutos_estimados, f.rango_min,
            f.rango_max, f.confianza if f.confianza is not None else "", f.nivel_ocupacion,
            "" if real is None else round(real, 2),
            "" if real is None else round(abs(f.minutos_estimados - real), 2),
        ])
    return Response(
        content="﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="waitless_predicciones.csv"'},
    )
