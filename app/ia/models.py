"""
WaitLess — Modelos de BD del módulo de IA
==========================================
  predicciones : cada estimación de tiempo de espera (y, cuando el pedido queda
                 listo, el tiempo REAL, para medir qué tan bien predijo el modelo)
  modelos_ia   : cada versión entrenada del modelo, con sus métricas y el archivo
                 serializado (así las versiones sobreviven a un reinicio/despliegue)
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, LargeBinary, String, Text,
)
from sqlalchemy.sql import func

from app.core.database import Base


def _utc_ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Prediccion(Base):
    __tablename__ = "predicciones"

    id = Column(Integer, primary_key=True, index=True)

    # ── Entradas que se le pasaron al modelo ──
    hora = Column(Integer, nullable=False)            # 0-23 (hora de Colombia)
    dia_semana = Column(Integer, nullable=False)      # 0=lunes … 6=domingo
    mesas_ocupadas = Column(Integer, nullable=False)  # carga del restaurante en ese momento
    total_items = Column(Integer, nullable=False)
    total_pedido = Column(Float, nullable=False)

    # ── Resultado ──
    minutos_estimados = Column(Integer, nullable=False)
    rango_min = Column(Integer, nullable=False)
    rango_max = Column(Integer, nullable=False)
    nivel_ocupacion = Column(String(10), nullable=False)   # bajo | medio | alto
    recomendacion = Column(Text, nullable=True)

    # ── Trazabilidad (RF: versión del modelo y variables usadas) ──
    confianza = Column(Integer, nullable=True)             # 0-100
    version_modelo = Column(Integer, nullable=True)        # 0 = modelo heredado
    fuente = Column(String(10), nullable=True)             # modelo | reglas
    restaurante_id = Column(Integer, nullable=True, index=True)

    # ── Evaluación: se llena cuando el pedido queda listo ──
    tiempo_real_minutos = Column(Float, nullable=True)
    pedido_id = Column(Integer, nullable=True, index=True)

    creado_en = Column(DateTime, server_default=func.now(), index=True)


class ModeloIA(Base):
    """Una versión entrenada del modelo."""
    __tablename__ = "modelos_ia"

    id = Column(Integer, primary_key=True, index=True)
    version = Column(Integer, nullable=False, unique=True, index=True)
    algoritmo = Column(String(60), nullable=False, default="RandomForestRegressor")
    motivo = Column(String(20), nullable=False, default="manual")   # manual | automatico | arranque
    variables = Column(Text, nullable=True)                         # JSON con las variables usadas

    muestras_reales = Column(Integer, nullable=False, default=0)
    muestras_sinteticas = Column(Integer, nullable=False, default=0)
    total_muestras = Column(Integer, nullable=False, default=0)

    mae = Column(Float, nullable=True)           # error medio en validación (min)
    r2 = Column(Float, nullable=True)
    mae_baseline = Column(Float, nullable=True)  # error de "predecir siempre el promedio"

    activo = Column(Boolean, nullable=False, default=False)
    archivo = Column(LargeBinary, nullable=True)  # pipeline serializado
    entrenado_en = Column(DateTime, default=_utc_ahora, index=True)
