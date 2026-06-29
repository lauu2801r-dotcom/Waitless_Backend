"""
WaitLess — Modelo de BD para Predicciones de IA
=================================================
Tabla: predicciones
Guarda cada consulta de predicción de tiempo de espera,
tanto las hechas por clientes como las del panel admin.
"""

from sqlalchemy import Column, Integer, Float, String, DateTime, Boolean, Text
from sqlalchemy.sql import func
from app.core.database import Base


class Prediccion(Base):
    __tablename__ = "predicciones"

    id                  = Column(Integer, primary_key=True, index=True)

    # ── Inputs que se le pasaron al modelo ──────────────────
    hora                = Column(Integer, nullable=False)          # 0-23
    dia_semana          = Column(Integer, nullable=False)          # 0=lunes…6=domingo
    mesas_ocupadas      = Column(Integer, nullable=False)
    total_items         = Column(Integer, nullable=False)
    total_pedido        = Column(Float,   nullable=False)

    # ── Resultado del modelo ────────────────────────────────
    minutos_estimados   = Column(Integer, nullable=False)
    rango_min           = Column(Integer, nullable=False)
    rango_max           = Column(Integer, nullable=False)
    nivel_ocupacion     = Column(String(10), nullable=False)       # bajo|medio|alto
    recomendacion       = Column(Text, nullable=True)

    # ── Metadatos ───────────────────────────────────────────
    # Si después el pedido se completa, el admin puede registrar
    # el tiempo real para evaluar la precisión del modelo
    tiempo_real_minutos = Column(Float, nullable=True)
    pedido_id           = Column(Integer, nullable=True)           # referencia opcional al pedido

    creado_en           = Column(DateTime, server_default=func.now())