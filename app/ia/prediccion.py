"""
WaitLess — Predicción de tiempo de espera (v2)
===============================================
- Usa el modelo ACTIVO (ver registro.py).
- Rango y nivel de confianza salen de lo que "opinan" los 100 árboles del
  Random Forest: si todos coinciden la confianza es alta; si discrepan, baja.
- Si el modelo falla o no existe, estima con reglas de negocio (RF: respaldo).
- Cada predicción se guarda con versión del modelo y variables, para auditoría
  y para compararla después con el tiempo real.
"""
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
from sqlalchemy.orm import Session

from app.ia import registro
from app.ia.entrenamiento import VARIABLES, hora_local, modelo_existe
from app.ia.models import Prediccion
from app.modules.pedidos.models import EstadoPedido, Pedido

logger = logging.getLogger(__name__)


def nivel_de_carga(carga: int) -> str:
    """Para mesas ocupadas (0-14)."""
    return "bajo" if carga <= 4 else ("medio" if carga <= 9 else "alto")


def nivel_cocina(pedidos_en_curso: int) -> str:
    """Para pedidos que la cocina tiene en curso."""
    return "bajo" if pedidos_en_curso <= 1 else ("medio" if pedidos_en_curso <= 3 else "alto")


def estimar_por_reglas(hora: int, dia_semana: int, carga: int, total_items: int) -> float:
    """Respaldo cuando no hay modelo: reglas simples de cocina."""
    t = 8.0 + carga * 0.4 + total_items * 1.2
    if 12 <= hora <= 14 or 19 <= hora <= 21:
        t += 7
    if dia_semana >= 5:
        t += 4
    return t


def _recomendacion(minutos: int) -> str:
    if minutos <= 10:
        return "🟢 Tu pedido estará listo muy pronto."
    if minutos <= 20:
        return "🟡 Tiempo de espera normal. ¡Gracias por tu paciencia!"
    return "🔴 Alta demanda en este momento. Te avisaremos cuando esté listo."


def _con_modelo(hora, dia_semana, carga, total_items, total_pedido, db):
    modelo, version = registro.obtener_modelo(db)
    x = np.array([[hora, dia_semana, carga, total_items, total_pedido]], dtype=float)
    xs = modelo.named_steps["scaler"].transform(x)
    arboles = np.array([t.predict(xs)[0] for t in modelo.named_steps["rf"].estimators_])
    media = float(arboles.mean())
    p10, p90 = float(np.percentile(arboles, 10)), float(np.percentile(arboles, 90))
    # Error típico del modelo (el 80 % de las veces se equivocó menos que esto, en validación)
    e80 = registro.error_p80_activo()
    if e80 is None:
        e80 = (p90 - p10) / 2.0
    # El rango cubre ≈ 80 % de los casos; es más ancho si los árboles discrepan.
    medio_ancho = max(e80, (p90 - p10) / 2.0)
    # Confianza: 100 % si el error esperado es 0; baja cuanto mayor sea frente al tiempo estimado.
    confianza = int(round(100 * (1.0 - min(1.0, medio_ancho / max(media, 1.0)))))
    return media, media - medio_ancho, media + medio_ancho, max(35, min(99, confianza)), version


def predecir_tiempo_espera(
    hora: int,
    dia_semana: int,
    mesas_ocupadas: int,
    total_items: int,
    total_pedido: float,
    db: Optional[Session] = None,
    pedido_id: Optional[int] = None,
    restaurante_id: Optional[int] = None,
    guardar: bool = True,
    carga_de_cocina: bool = False,
) -> dict:
    """`mesas_ocupadas` = carga del restaurante (pedidos en cocina / mesas ocupadas)."""
    fuente = "modelo"
    try:
        media, p10, p90, confianza, version = _con_modelo(
            hora, dia_semana, mesas_ocupadas, total_items, total_pedido, db)
    except Exception as e:  # noqa: BLE001
        logger.warning("Modelo no disponible, se usan reglas de negocio: %s", e)
        fuente, version, confianza = "reglas", None, 50
        media = estimar_por_reglas(hora, dia_semana, mesas_ocupadas, total_items)
        p10, p90 = media * 0.8, media * 1.2

    minutos = round(max(3.0, min(media, 90.0)))
    rango_min = max(1, min(minutos - 1, math.floor(p10)))
    rango_max = max(minutos + 1, math.ceil(p90))
    nivel = nivel_cocina(mesas_ocupadas) if carga_de_cocina else nivel_de_carga(mesas_ocupadas)
    recomendacion = _recomendacion(minutos)

    prediccion_id = None
    if db is not None and guardar:
        try:
            reg = Prediccion(
                hora=hora, dia_semana=dia_semana, mesas_ocupadas=mesas_ocupadas,
                total_items=total_items, total_pedido=total_pedido,
                minutos_estimados=minutos, rango_min=rango_min, rango_max=rango_max,
                nivel_ocupacion=nivel, recomendacion=recomendacion,
                confianza=confianza, version_modelo=version, fuente=fuente,
                restaurante_id=restaurante_id, pedido_id=pedido_id,
            )
            db.add(reg)
            db.commit()
            db.refresh(reg)
            prediccion_id = reg.id
        except Exception as e:  # noqa: BLE001
            db.rollback()
            logger.error("No se pudo guardar la predicción: %s", e)

    return {
        "id": prediccion_id,
        "minutos_estimados": minutos,
        "rango_min": rango_min,
        "rango_max": rango_max,
        "nivel_ocupacion": nivel,
        "recomendacion": recomendacion,
        "confianza": confianza,
        "version_modelo": version,
        "fuente": fuente,
        "variables": VARIABLES,
        "hora_consulta": datetime.now().isoformat(),
    }


# ───────────────────────── Afluencia por hora ─────────────────────────
def _curva_por_modelo(dia_semana: int, db: Optional[Session]) -> list:
    horas = range(10, 23)
    out = []
    for h in horas:
        carga = 11 if (12 <= h <= 14 or 19 <= h <= 21) else (6 if 15 <= h <= 18 else 3)
        try:
            media, *_ = _con_modelo(h, dia_semana, carga, 3, 45_000.0, db)
        except Exception:  # noqa: BLE001
            media = estimar_por_reglas(h, dia_semana, carga, 3)
        out.append((h, round(min(100, max(5, (media / 35.0) * 80 + 5)))))
    return out


def _etiqueta(h: int) -> str:
    h12 = h if h <= 12 else h - 12
    return f"{h12}{'am' if h < 12 else 'pm'}"


def predecir_afluencia_hora(
    dia_semana: int, db: Optional[Session] = None, restaurante_id: Optional[int] = None,
) -> list:
    """
    Curva de afluencia por hora. Si el restaurante ya tiene historial se calcula con
    SUS pedidos reales de las últimas 8 semanas (mismo día de la semana); si aún no
    tiene suficientes, se estima con el modelo.
    """
    conteo = {h: 0 for h in range(10, 23)}
    fechas = set()
    total = 0
    fuente = "modelo"
    if db is not None:
        desde = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=56)
        q = db.query(Pedido.creado_en).filter(
            Pedido.creado_en >= desde, Pedido.estado != EstadoPedido.cancelado)
        if restaurante_id is not None:
            q = q.filter(Pedido.restaurante_id == restaurante_id)
        for (c,) in q.all():
            if c is None:
                continue
            loc = hora_local(c)
            if loc.weekday() == dia_semana and loc.hour in conteo:
                conteo[loc.hour] += 1
                fechas.add(loc.date())
                total += 1

    if total >= 12:
        fuente = "historial"
        dias = max(1, len(fechas))
        prom = {h: conteo[h] / dias for h in conteo}
        mx = max(prom.values()) or 1.0
        curva = [(h, round(5 + 90 * prom[h] / mx)) for h in conteo]
    else:
        curva = _curva_por_modelo(dia_semana, db)

    return [
        {"hora": f"{h:02d}:00", "hora_label": _etiqueta(h), "ocupacion_pct": pct,
         "es_pico": pct >= 75, "fuente": fuente}
        for h, pct in curva
    ]


# ───────────────────────── Historial e info ─────────────────────────
def obtener_historial(db: Session, restaurante_id: Optional[int] = None, limite: int = 50) -> list:
    q = db.query(Prediccion)
    if restaurante_id is not None:
        q = q.filter(Prediccion.restaurante_id == restaurante_id)
    return [
        {
            "id": r.id, "pedido_id": r.pedido_id, "hora": r.hora, "dia_semana": r.dia_semana,
            "mesas_ocupadas": r.mesas_ocupadas, "total_items": r.total_items,
            "minutos_estimados": r.minutos_estimados, "rango_min": r.rango_min,
            "rango_max": r.rango_max, "confianza": r.confianza,
            "version_modelo": r.version_modelo, "fuente": r.fuente,
            "nivel_ocupacion": r.nivel_ocupacion,
            "tiempo_real_minutos": r.tiempo_real_minutos,
            "creado_en": r.creado_en.isoformat() if r.creado_en else None,
        }
        for r in q.order_by(Prediccion.id.desc()).limit(limite).all()
    ]


def info_modelo(db: Optional[Session] = None) -> dict:
    if not modelo_existe(db):
        return {"modelo_disponible": False, "mensaje": "El modelo aún no ha sido entrenado."}
    from app.ia.models import ModeloIA
    propia = db is None
    if propia:
        from app.core.database import SessionLocal
        db = SessionLocal()
    try:
        fila = (db.query(ModeloIA).filter(ModeloIA.activo.is_(True))
                .order_by(ModeloIA.version.desc()).first())
        if fila is None:
            return {"modelo_disponible": True, "version": 0, "mensaje": "Modelo heredado (sin versionar)."}
        return {
            "modelo_disponible": True,
            "version": fila.version,
            "algoritmo": fila.algoritmo,
            "entrenado_en": fila.entrenado_en.isoformat() if fila.entrenado_en else None,
            "muestras_reales": fila.muestras_reales,
            "muestras_sinteticas": fila.muestras_sinteticas,
            "mae_minutos": fila.mae,
            "r2_score": fila.r2,
            "variables": VARIABLES,
        }
    finally:
        if propia:
            db.close()
