"""
WaitLess — Métricas del modelo de IA (v2)
==========================================
Se calculan SOLO con predicciones reales ya cerradas: lo que el modelo estimó al
crear cada pedido contra el tiempo que de verdad tardó (tabla `predicciones`).

  MAE                  error absoluto medio, en minutos
  precisión (±5 min)   % de pedidos cuyo error fue de 5 minutos o menos
  acierto por rango    % de pedidos cuyo tiempo real cayó dentro del rango predicho
  por categoría        lo anterior separado por nivel de carga (bajo / medio / alto)
  por versión          para comparar versiones del modelo entre sí
  alertas              cuando una métrica pasa el umbral configurado
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.ia.models import ModeloIA, Prediccion
from app.ia.entrenamiento import modelo_existe

UMBRAL_MAE_MIN = 8.0          # minutos
UMBRAL_PRECISION_MIN = 50.0   # % dentro de ±5 min
MIN_MUESTRAS_ALERTA = 10


def _filtrar(db: Session, restaurante_id, version, desde, hasta, solo_cerradas=True):
    q = db.query(Prediccion).filter(Prediccion.fuente == "modelo")
    if solo_cerradas:
        q = q.filter(Prediccion.tiempo_real_minutos.isnot(None))
    if restaurante_id is not None:
        q = q.filter(Prediccion.restaurante_id == restaurante_id)
    if version is not None:
        q = q.filter(Prediccion.version_modelo == version)
    if desde is not None:
        q = q.filter(Prediccion.creado_en >= desde)
    if hasta is not None:
        q = q.filter(Prediccion.creado_en <= hasta)
    return q


def _resumen(filas: List[Prediccion]) -> dict:
    n = len(filas)
    if n == 0:
        return {"n": 0, "mae": None, "precision_5min_pct": None, "acierto_rango_pct": None}
    errores = [abs(f.minutos_estimados - f.tiempo_real_minutos) for f in filas]
    en_rango = sum(1 for f in filas if f.rango_min <= f.tiempo_real_minutos <= f.rango_max)
    return {
        "n": n,
        "mae": round(sum(errores) / n, 2),
        "precision_5min_pct": round(sum(1 for e in errores if e <= 5) / n * 100, 1),
        "acierto_rango_pct": round(en_rango / n * 100, 1),
    }


def calcular_metricas_modelo(
    db: Session,
    restaurante_id: Optional[int] = None,
    version: Optional[int] = None,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    umbral_mae: float = UMBRAL_MAE_MIN,
    umbral_precision: float = UMBRAL_PRECISION_MIN,
) -> dict:
    if not modelo_existe(db):
        return {"modelo_disponible": False,
                "mensaje": "El modelo aún no ha sido entrenado. Usa POST /ia/entrenar"}

    activa = (db.query(ModeloIA).filter(ModeloIA.activo.is_(True))
              .order_by(ModeloIA.version.desc()).first())
    filas = _filtrar(db, restaurante_id, version, desde, hasta).order_by(Prediccion.id).all()
    n = len(filas)
    base = {
        "modelo_disponible": True,
        "version_activa": activa.version if activa else 0,
        "filtros": {
            "restaurante_id": restaurante_id, "version": version,
            "desde": desde.isoformat() if desde else None,
            "hasta": hasta.isoformat() if hasta else None,
        },
        "umbrales": {"mae_max_min": umbral_mae, "precision_min_pct": umbral_precision},
        "calculado_en": datetime.now().isoformat(),
    }

    alertas: List[dict] = []
    if activa and activa.muestras_sinteticas:
        pct = round(activa.muestras_sinteticas / max(activa.total_muestras, 1) * 100)
        alertas.append({
            "nivel": "info", "codigo": "datos_arranque",
            "mensaje": f"La versión {activa.version} se entrenó con {pct}% de datos de arranque "
                       f"({activa.muestras_reales} pedidos reales). Mejorará al reentrenar con más pedidos.",
        })

    if n == 0:
        alertas.append({"nivel": "info", "codigo": "sin_datos",
                        "mensaje": "Aún no hay pedidos con tiempo real para evaluar el modelo."})
        return {**base, "total_pedidos_evaluados": 0, "alertas": alertas, "por_version": [],
                "por_categoria": {}, "anomalias": [],
                "mensaje": "Sin pedidos completados con predicción para evaluar."}

    reales = [f.tiempo_real_minutos for f in filas]
    preds = [f.minutos_estimados for f in filas]
    errores = [abs(p - r) for p, r in zip(preds, reales)]
    res = _resumen(filas)
    prom_real = sum(reales) / n
    mae_base = sum(abs(r - prom_real) for r in reales) / n
    sesgo = sum(p - r for p, r in zip(preds, reales)) / n

    por_categoria = {}
    for nivel in ("bajo", "medio", "alto"):
        sub = [f for f in filas if f.nivel_ocupacion == nivel]
        r = _resumen(sub)
        por_categoria[nivel] = {"n": r["n"], "mae": r["mae"],
                                "acierto_pct": r["precision_5min_pct"]}

    por_version = []
    for v in sorted({f.version_modelo for f in filas if f.version_modelo is not None}):
        r = _resumen([f for f in filas if f.version_modelo == v])
        por_version.append({"version": v, **r})

    if n >= MIN_MUESTRAS_ALERTA:
        if res["mae"] > umbral_mae:
            alertas.append({"nivel": "alta", "codigo": "mae_alto",
                            "mensaje": f"El error medio ({res['mae']} min) supera el umbral de {umbral_mae} min. "
                                       "Conviene reentrenar el modelo."})
        if res["precision_5min_pct"] < umbral_precision:
            alertas.append({"nivel": "alta", "codigo": "precision_baja",
                            "mensaje": f"Solo {res['precision_5min_pct']}% de las predicciones acierta a ±5 min "
                                       f"(mínimo esperado {umbral_precision}%)."})
        if abs(sesgo) > 5:
            alertas.append({"nivel": "media", "codigo": "sesgo",
                            "mensaje": "El modelo tiende a " + ("sobreestimar" if sesgo > 0 else "subestimar")
                                       + f" los tiempos (≈ {abs(round(sesgo, 1))} min en promedio)."})
    else:
        alertas.append({"nivel": "info", "codigo": "pocos_datos",
                        "mensaje": f"Solo {n} pedidos evaluados; las alertas se activan desde {MIN_MUESTRAS_ALERTA}."})

    anomalias = [
        {"prediccion_id": f.id, "pedido_id": f.pedido_id, "estimado": f.minutos_estimados,
         "real": round(f.tiempo_real_minutos, 1),
         "error": round(abs(f.minutos_estimados - f.tiempo_real_minutos), 1),
         "creado_en": f.creado_en.isoformat() if f.creado_en else None}
        for f in filas if abs(f.minutos_estimados - f.tiempo_real_minutos) > 15
    ][-10:]
    if anomalias:
        alertas.append({"nivel": "media", "codigo": "anomalias",
                        "mensaje": f"{len(anomalias)} predicciones recientes se desviaron más de 15 min."})

    return {
        **base,
        "total_pedidos_evaluados": n,
        "mae_minutos": res["mae"],
        "precision_general_pct": res["precision_5min_pct"],
        "precision_5min_pct": res["precision_5min_pct"],
        "precision_10min_pct": round(sum(1 for e in errores if e <= 10) / n * 100, 1),
        "acierto_rango_pct": res["acierto_rango_pct"],
        "tiempo_promedio_real_min": round(prom_real, 2),
        "tiempo_promedio_predicho_min": round(sum(preds) / n, 2),
        "mae_baseline_minutos": round(mae_base, 2),
        "mejora_vs_baseline_pct": round((1 - res["mae"] / mae_base) * 100, 1) if mae_base > 0 else None,
        "sesgo_minutos": round(sesgo, 2),
        "distribucion_errores": {
            "0_a_5_min": sum(1 for e in errores if e <= 5),
            "5_a_10_min": sum(1 for e in errores if 5 < e <= 10),
            "10_a_20_min": sum(1 for e in errores if 10 < e <= 20),
            "mas_de_20_min": sum(1 for e in errores if e > 20),
        },
        "por_categoria": por_categoria,
        "por_version": por_version,
        "anomalias": anomalias,
        "alertas": alertas,
    }


def listar_versiones(db: Session) -> List[dict]:
    import json
    out = []
    for m in db.query(ModeloIA).order_by(ModeloIA.version.desc()).all():
        real = _resumen(_filtrar(db, None, m.version, None, None).all())
        out.append({
            "id": m.id, "version": m.version, "activo": bool(m.activo), "motivo": m.motivo,
            "algoritmo": m.algoritmo,
            "entrenado_en": m.entrenado_en.isoformat() if m.entrenado_en else None,
            "muestras_reales": m.muestras_reales, "muestras_sinteticas": m.muestras_sinteticas,
            "total_muestras": m.total_muestras, "mae_entrenamiento": m.mae, "r2": m.r2,
            "mae_baseline": m.mae_baseline,
            "variables": json.loads(m.variables) if m.variables else [],
            "predicciones_evaluadas": real["n"], "mae_produccion": real["mae"],
        })
    return out


def filas_para_exportar(db: Session, restaurante_id, version, desde, hasta) -> List[Prediccion]:
    return (_filtrar(db, restaurante_id, version, desde, hasta, solo_cerradas=False)
            .order_by(Prediccion.id).all())
