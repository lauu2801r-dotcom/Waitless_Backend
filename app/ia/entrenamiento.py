"""
WaitLess — Entrenamiento del modelo de IA (v2)
===============================================
Modelo: Random Forest que predice los MINUTOS que tarda la cocina en dejar listo
un pedido (desde que se crea hasta que pasa a "listo").

Variables (todas se conocen en el momento de crear el pedido):
  hora_del_dia          hora LOCAL de Colombia (0-23)
  dia_semana            0=lunes … 6=domingo
  carga_del_restaurante pedidos que la cocina del restaurante tenía en curso en ese momento
  total_items           cantidad de platos del pedido
  total_pedido          valor del pedido

Objetivo (y): minutos entre creado_en y listo_en (si el pedido es antiguo y no tiene
listo_en se usa actualizado_en). Se descartan tiempos < 1 min o > 3 horas.

Cada entrenamiento crea una VERSIÓN nueva en `modelos_ia` con sus métricas
(MAE, R², y el error de un modelo "tonto" que siempre predice el promedio, para
comparar). El modelo activo es el que se usa para predecir.
"""
import json
import logging
import pickle
import threading
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy.orm import Session

from app.ia import registro
from app.ia.models import ModeloIA
from app.modules.pedidos.models import EstadoPedido, Pedido

logger = logging.getLogger(__name__)

VARIABLES = ["hora_del_dia", "dia_semana", "carga_del_restaurante", "total_items", "total_pedido"]
MIN_MUESTRAS_REALES = 30          # con menos se completa con datos de arranque
AUTO_REENTRENAR_CADA = 25         # pedidos reales nuevos para reentrenar solo
TOLERANCIA_AUTO = 1.05            # un modelo automático solo se activa si no empeora más de 5 %
UTC_MENOS_5 = timedelta(hours=-5)  # Colombia no tiene horario de verano

_entrenando = threading.Lock()


def hora_local(dt_utc: datetime) -> datetime:
    """El servidor guarda las fechas en UTC; el modelo aprende con la hora de Colombia."""
    return dt_utc + UTC_MENOS_5


def _utc_ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ─────────────────────────── Extracción de datos ───────────────────────────
def _fin_de(p: Pedido) -> Optional[datetime]:
    return p.listo_en or (p.actualizado_en if p.estado in (EstadoPedido.listo, EstadoPedido.entregado) else None)


def _cargas(inicios: np.ndarray, fines: np.ndarray) -> np.ndarray:
    """
    Para cada pedido: cuántos OTROS pedidos del mismo restaurante estaban en cocina
    cuando él se creó (creados antes y todavía sin terminar).
    """
    n = len(inicios)
    salida = np.zeros(n, dtype=int)
    paso = 500
    for a in range(0, n, paso):
        b = min(n, a + paso)
        i = inicios[a:b, None]
        activo = (inicios[None, :] <= i) & (fines[None, :] > i)
        salida[a:b] = activo.sum(axis=1) - 1  # se descuenta el propio pedido
    return np.maximum(salida, 0)


def extraer_dataset(db: Session) -> Tuple[List[list], List[float]]:
    pedidos = (
        db.query(Pedido)
        .filter(Pedido.estado != EstadoPedido.cancelado, Pedido.creado_en.isnot(None))
        .all()
    )
    ahora = _utc_ahora()
    por_rest: dict = {}
    for p in pedidos:
        por_rest.setdefault(p.restaurante_id, []).append(p)

    X: List[list] = []
    y: List[float] = []
    for lista in por_rest.values():
        lista.sort(key=lambda p: p.creado_en)
        t0 = lista[0].creado_en
        seg = lambda d: (d - t0).total_seconds()  # noqa: E731
        inicios = np.array([seg(p.creado_en) for p in lista])
        fines = np.array([seg(_fin_de(p) or ahora) for p in lista])
        cargas = _cargas(inicios, fines)
        for p, carga in zip(lista, cargas):
            fin = _fin_de(p)
            if fin is None:
                continue
            minutos = (fin - p.creado_en).total_seconds() / 60.0
            if not (1 <= minutos <= 180):
                continue
            local = hora_local(p.creado_en)
            items = sum(it.cantidad for it in p.items)
            X.append([local.hour, local.weekday(), int(carga), items, float(p.total or 0)])
            y.append(round(minutos, 2))
    return X, y


def datos_de_arranque(n: int = 300) -> Tuple[List[list], List[float]]:
    """Datos simulados con lógica de cocina, SOLO para arrancar cuando hay pocos pedidos reales."""
    rng = np.random.default_rng(seed=42)
    X, y = [], []
    for _ in range(n):
        hora = int(rng.integers(10, 23))
        dia = int(rng.integers(0, 7))
        carga = int(rng.integers(0, 15))
        items = int(rng.integers(1, 10))
        total = round(float(rng.uniform(15_000, 120_000)), 2)
        t = 8.0
        if 12 <= hora <= 14 or 19 <= hora <= 21:
            t += rng.uniform(4, 10)
        if dia >= 5:
            t += rng.uniform(2, 6)
        t += carga * 0.4 + items * 1.2 + rng.normal(0, 1.5)
        X.append([hora, dia, carga, items, total])
        y.append(round(max(3.0, min(t, 60.0)), 2))
    return X, y


# ───────────────────────────── Entrenamiento ─────────────────────────────
def entrenar_modelo(db: Session, motivo: str = "manual") -> dict:
    """
    Entrena una versión nueva. `motivo`: manual | automatico | arranque.
    Las versiones manuales y de arranque quedan activas; las automáticas solo si
    no empeoran el error de la versión activa.
    """
    with _entrenando:
        X_real, y_real = extraer_dataset(db)
        n_real = len(X_real)
        n_sint = 0
        X_all, y_all = list(X_real), list(y_real)
        pesos = [3.0] * n_real  # los pedidos reales pesan más que los de arranque

        if n_real < MIN_MUESTRAS_REALES:
            Xs, ys = datos_de_arranque()
            n_sint = len(Xs)
            X_all += Xs
            y_all += ys
            pesos += [1.0] * n_sint

        X = np.array(X_all, dtype=float)
        y = np.array(y_all, dtype=float)
        w = np.array(pesos, dtype=float)

        if len(X) >= 40:
            Xtr, Xte, ytr, yte, wtr, _ = train_test_split(X, y, w, test_size=0.2, random_state=42)
        else:
            Xtr, Xte, ytr, yte, wtr = X, X, y, y, w

        pipe = Pipeline([
            ("scaler", StandardScaler()),
            ("rf", RandomForestRegressor(
                n_estimators=100, max_depth=8, min_samples_leaf=3, random_state=42, n_jobs=-1)),
        ])
        pipe.fit(Xtr, ytr, rf__sample_weight=wtr)

        pred = pipe.predict(Xte)
        mae = round(float(mean_absolute_error(yte, pred)), 2)
        r2 = round(float(r2_score(yte, pred)), 4)
        mae_base = round(float(mean_absolute_error(yte, np.full_like(yte, ytr.mean()))), 2)

        previa = (
            db.query(ModeloIA).filter(ModeloIA.activo.is_(True))
            .order_by(ModeloIA.version.desc()).first()
        )
        ultima = db.query(ModeloIA).order_by(ModeloIA.version.desc()).first()
        version = (ultima.version if ultima else 0) + 1

        if motivo == "automatico" and previa is not None and previa.mae is not None:
            activar = mae <= previa.mae * TOLERANCIA_AUTO
        else:
            activar = True

        fila = ModeloIA(
            version=version, motivo=motivo, variables=json.dumps(VARIABLES),
            muestras_reales=n_real, muestras_sinteticas=n_sint, total_muestras=len(X),
            mae=mae, r2=r2, mae_baseline=mae_base, activo=False,
            archivo=pickle.dumps(pipe), entrenado_en=_utc_ahora(),
        )
        db.add(fila)
        db.flush()
        if activar:
            db.query(ModeloIA).filter(ModeloIA.id != fila.id).update({ModeloIA.activo: False})
            fila.activo = True
        db.commit()
        registro.invalidar()

        logger.info("Modelo v%s entrenado: MAE=%s R2=%s activo=%s", version, mae, r2, activar)
        return {
            "version": version,
            "activo": activar,
            "motivo": motivo,
            "muestras_reales": n_real,
            "muestras_sinteticas": n_sint,
            "total_muestras": len(X),
            "mae_minutos": mae,
            "mae_baseline_minutos": mae_base,
            "r2_score": r2,
            "variables": VARIABLES,
            "entrenado_en": fila.entrenado_en.isoformat(),
            "mensaje": (
                "Versión activada." if activar else
                "La versión nueva empeora el error de la activa, por eso quedó guardada pero sin activar."
            ),
        }


def activar_version(db: Session, version_id: int) -> Optional[ModeloIA]:
    fila = db.query(ModeloIA).filter(ModeloIA.id == version_id).first()
    if not fila or fila.archivo is None:
        return None
    db.query(ModeloIA).filter(ModeloIA.id != fila.id).update({ModeloIA.activo: False})
    fila.activo = True
    db.commit()
    registro.invalidar()
    return fila


def reentrenar_en_segundo_plano() -> None:
    """Lanza un entrenamiento automático sin hacer esperar la petición que lo disparó."""
    from app.core.database import SessionLocal

    def _tarea():
        if _entrenando.locked():
            return
        s = SessionLocal()
        try:
            entrenar_modelo(s, motivo="automatico")
        except Exception as e:  # noqa: BLE001
            logger.warning("Reentrenamiento automático falló: %s", e)
        finally:
            s.close()

    threading.Thread(target=_tarea, daemon=True).start()


def modelo_existe(db: Optional[Session] = None) -> bool:
    return registro.hay_modelo(db)
