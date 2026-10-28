"""
Historial SIMULADO para demostración (IA y Power BI)
=====================================================
Carga semanas de operación realista en los restaurantes que ya tienes: pedidos con
sus platos, tiempos de cocina, pagos, facturas, calificaciones y predicciones de la IA.

    python -m app.core.seed_historial               # 60 días
    python -m app.core.seed_historial --dias 90
    python -m app.core.seed_historial --borrar      # elimina SOLO lo que creó este script

IMPORTANTE (para el documento): estos datos son SIMULADOS. Sirven para entrenar el modelo
con volumen y para que el tablero de Power BI tenga qué mostrar. Todo lo que crea queda
marcado con clientes @demo.waitless, así se puede borrar sin tocar tus datos reales.

Cómo se simulan los tiempos de cocina: dependen de los platos (una bebida sale en 2 min,
un plato fuerte en 12), de cuántos platos lleva el pedido, de la hora (almuerzo y cena
son más lentos), del fin de semana y de cuántos pedidos tenía la cocina en ese momento,
más un ruido aleatorio. Así el modelo tiene una relación real que aprender, pero nunca
será perfecto (como pasa en la vida real).
"""
import argparse
import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import List

import numpy as np

from app.core.database import Base, SessionLocal, engine
from app.core.migraciones import asegurar_columnas
from app.core.security import get_password_hash
from app.ia.entrenamiento import entrenar_modelo, hora_local
from app.ia.models import ModeloIA, Prediccion
from app.ia.prediccion import predecir_tiempo_espera
from app.modules.auth.models import Restaurante, RolUsuario, Usuario
from app.modules.calificaciones.models import Calificacion
from app.modules.mesas.models import Mesa
from app.modules.menu.models import Producto
from app.modules.notificaciones.models import Notificacion
from app.modules.pagos.models import EstadoFactura, EstadoPago, Factura, MetodoPago, Pago
from app.modules.pagos.service import IMPUESTO_PORCENTAJE, _impuesto
from app.modules.pedidos.models import EstadoPedido, ItemPedido, Pedido

DOMINIO = "@demo.waitless"
N_CLIENTES = 30
DIAS_HOLDOUT = 15  # los últimos días llevan predicción de la IA hecha con un modelo entrenado ANTES

NOMBRES = ["Camila", "Daniela", "Santiago", "Valeria", "Mateo", "Sofía", "Andrés", "Laura", "Felipe",
           "Juliana", "Sebastián", "Natalia", "David", "Paula", "Nicolás", "Carolina", "Jorge", "Mariana",
           "Esteban", "Luisa", "Camilo", "Isabela", "Julián", "Manuela", "Tomás", "Gabriela", "Diego",
           "Sara", "Alejandro", "Catalina"]
APELLIDOS = ["Gómez", "Rodríguez", "Martínez", "López", "Hernández", "Ramírez", "Torres", "Díaz", "Vargas", "Rojas"]

HORAS = list(range(11, 23))
PESO_HORA = [0.03, 0.14, 0.16, 0.09, 0.04, 0.03, 0.04, 0.10, 0.17, 0.12, 0.06, 0.02]
PREP = {"entradas": 5, "principales": 12, "postres": 4, "bebidas": 2, "hamburguesas": 10,
        "perros calientes": 7, "combos": 12, "acompañantes": 5}
METODOS = [(MetodoPago.tarjeta, 0.45), (MetodoPago.efectivo, 0.25),
           (MetodoPago.billetera, 0.18), (MetodoPago.transferencia, 0.12)]
COMENT_BUENOS = ["Todo delicioso, volveré.", "Excelente atención y muy rápido.", "Muy buena presentación.",
                 "El sabor increíble.", "Lo recomiendo totalmente."]
COMENT_REGULARES = ["Estuvo bien, pero demoró un poco.", "Rico, aunque llegó tibio.", "Normal, nada especial."]
COMENT_MALOS = ["Demoró demasiado.", "El plato llegó frío.", "No estuvo como esperaba."]


def _utc_ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _a_utc(local: datetime) -> datetime:
    return local + timedelta(hours=5)


# ─────────────────────────── borrar ───────────────────────────
def borrar(db) -> None:
    usuarios = db.query(Usuario).filter(Usuario.email.like(f"%{DOMINIO}")).all()
    if not usuarios:
        print("No hay datos simulados que borrar.")
        return
    uids = [u.id for u in usuarios]
    pids = [p for (p,) in db.query(Pedido.id).filter(Pedido.usuario_id.in_(uids)).all()]
    if pids:
        db.query(Calificacion).filter(Calificacion.pedido_id.in_(pids)).delete(synchronize_session=False)
        db.query(Pago).filter(Pago.pedido_id.in_(pids)).delete(synchronize_session=False)
        db.query(Factura).filter(Factura.pedido_id.in_(pids)).delete(synchronize_session=False)
        db.query(Prediccion).filter(Prediccion.pedido_id.in_(pids)).delete(synchronize_session=False)
        db.query(ItemPedido).filter(ItemPedido.pedido_id.in_(pids)).delete(synchronize_session=False)
        db.query(Pedido).filter(Pedido.id.in_(pids)).delete(synchronize_session=False)
    db.query(Notificacion).filter(Notificacion.usuario_id.in_(uids)).delete(synchronize_session=False)
    db.query(Usuario).filter(Usuario.id.in_(uids)).delete(synchronize_session=False)
    db.commit()
    print(f"🗑️  Borrados {len(pids)} pedidos simulados y {len(uids)} clientes demo.")


# ─────────────────────────── generar ───────────────────────────
def _clientes(db) -> List[int]:
    existentes = db.query(Usuario).filter(Usuario.email.like(f"%{DOMINIO}")).all()
    if existentes:
        return [u.id for u in existentes]
    clave = get_password_hash("Demo2026!")
    nuevos = []
    for i in range(N_CLIENTES):
        nuevos.append(Usuario(
            nombre=NOMBRES[i % len(NOMBRES)], apellido=APELLIDOS[i % len(APELLIDOS)],
            email=f"cliente{i + 1:02d}{DOMINIO}", hashed_password=clave, rol=RolUsuario.cliente,
            verificado=True, activo=True,
        ))
    db.add_all(nuevos)
    db.commit()
    return [u.id for u in nuevos]


def _minutos_cocina(rng, items_cat, n_items, hora, wd, carga) -> float:
    base = max((PREP.get((c or "").strip().lower(), 8) for c in items_cat), default=8)
    t = base + 1.4 * (n_items - 1) + 0.55 * carga + rng.normal(0, 1.8)
    if 12 <= hora <= 14 or 19 <= hora <= 21:
        t += 5.5
    if wd >= 5:
        t += 2.5
    return float(max(3.0, min(t, 70.0)))


def _pedidos_de_dia(rng, db_rest, productos, mesas, clientes, dia_local, tope_utc, estado):
    """Genera los pedidos de UN restaurante en UN día (cocina que se vacía cada noche)."""
    wd = dia_local.weekday()
    n = int(rng.integers(28, 52) * db_rest["escala"])
    n = int(n * (1.5 if wd >= 5 else (1.25 if wd == 4 else 1.0)))
    horas = rng.choice(HORAS, size=n, p=PESO_HORA)
    momentos = sorted(
        datetime(dia_local.year, dia_local.month, dia_local.day, int(h), int(rng.integers(0, 60)), int(rng.integers(0, 60)))
        for h in horas
    )
    activos: List[datetime] = []
    salida = []
    for local in momentos:
        creado = _a_utc(local)
        if creado > tope_utc:
            continue
        activos = [f for f in activos if f > creado]
        carga = len(activos)

        k = int(rng.choice([1, 2, 3, 4], p=[0.3, 0.4, 0.2, 0.1]))
        elegidos = rng.choice(len(productos), size=min(k, len(productos)), replace=False)
        items = []
        for idx in elegidos:
            p = productos[int(idx)]
            cant = int(rng.choice([1, 2], p=[0.8, 0.2]))
            items.append((p, cant))
        total = float(sum(p.precio * c for p, c in items))
        n_items = sum(c for _, c in items)

        if rng.random() < 0.03:
            ped = Pedido(usuario_id=int(rng.choice(clientes)), mesa_id=int(rng.choice(mesas)),
                         restaurante_id=db_rest["id"], estado=EstadoPedido.cancelado, total=total,
                         creado_en=creado, actualizado_en=creado + timedelta(minutes=3))
            minutos = None
        else:
            minutos = _minutos_cocina(rng, [p.categoria for p, _ in items], n_items, local.hour, wd, carga)
            listo = creado + timedelta(minutes=minutos)
            activos.append(listo)
            ped = Pedido(usuario_id=int(rng.choice(clientes)), mesa_id=int(rng.choice(mesas)),
                         restaurante_id=db_rest["id"], estado=estado, total=total, creado_en=creado,
                         listo_en=listo, actualizado_en=listo + timedelta(minutes=float(rng.uniform(5, 15))))
        ped.items = [ItemPedido(producto_id=p.id, cantidad=c, precio_unitario=p.precio, subtotal=p.precio * c)
                     for p, c in items]
        salida.append({"pedido": ped, "items": items, "carga": carga, "minutos": minutos, "local": local})
    return salida


def _cobrar_y_calificar(db, rng, lote, restaurante_nombre, efecto_plato, emails, ahora):
    pendientes = []  # (factura, datos del pago, calificaciones)
    for r in lote:
        ped, minutos = r["pedido"], r["minutos"]
        if minutos is None:
            continue
        pagado_en = ped.listo_en + timedelta(minutes=float(rng.uniform(5, 25)))
        if pagado_en > ahora:
            continue
        subtotal = round(ped.total, 2)
        impuesto = _impuesto(subtotal)
        propina = 0.0 if rng.random() < 0.55 else round(subtotal * float(rng.choice([0.05, 0.08, 0.10])), -2)
        total = round(subtotal + impuesto + propina, 2)
        metodo = MetodoPago(rng.choice([m.value for m, _ in METODOS], p=[w for _, w in METODOS]))

        if rng.random() < 0.04 and metodo != MetodoPago.efectivo:
            db.add(Pago(pedido_id=ped.id, metodo=metodo, monto=total, estado=EstadoPago.rechazado,
                        referencia=None, motivo_rechazo="Fondos insuficientes", usuario_id=ped.usuario_id,
                        usuario_email=emails[ped.usuario_id], creado_en=pagado_en - timedelta(minutes=1)))
        snapshot = {
            "concepto": f"Pedido #{ped.id}", "restaurante": restaurante_nombre,
            "cliente_email": emails[ped.usuario_id],
            "items": [{"nombre": p.nombre, "cantidad": c, "precio_unitario": p.precio, "subtotal": p.precio * c}
                      for p, c in r["items"]],
        }
        fac = Factura(pedido_id=ped.id, usuario_id=ped.usuario_id, subtotal=subtotal,
                      impuesto_pct=IMPUESTO_PORCENTAJE, impuesto=impuesto, propina=propina, total=total,
                      metodo=metodo, estado=EstadoFactura.pagada, pagado_en=pagado_en, creado_en=pagado_en,
                      detalle=json.dumps(snapshot, ensure_ascii=False))
        pago = dict(pedido_id=ped.id, metodo=metodo, monto=total, estado=EstadoPago.aprobado,
                    referencia=f"SIM-{uuid.uuid4().hex[:10].upper()}", usuario_id=ped.usuario_id,
                    usuario_email=emails[ped.usuario_id], creado_en=pagado_en)

        cals = []
        if rng.random() < 0.55:
            cuando = min(ahora, pagado_en + timedelta(minutes=float(rng.uniform(10, 90))))
            comentario = None
            for p, _ in r["items"]:
                mu = 4.5 - 0.05 * max(0.0, minutos - 12) - efecto_plato.get(p.id, 0.0)
                est = int(max(1, min(5, round(rng.normal(mu, 0.9)))))
                if comentario is None and rng.random() < 0.3:
                    comentario = random.choice(COMENT_BUENOS if est >= 4 else (COMENT_REGULARES if est == 3 else COMENT_MALOS))
                cals.append(Calificacion(usuario_id=ped.usuario_id, pedido_id=ped.id, producto_id=p.id,
                                         restaurante_id=ped.restaurante_id, estrellas=est,
                                         comentario=comentario, creado_en=cuando))
        pendientes.append((fac, pago, cals))

    # Una sola ida a la base para todas las facturas (así es rápido también en Neon)
    db.add_all([f for f, _, _ in pendientes])
    db.flush()
    for fac, pago, cals in pendientes:
        fac.numero = f"F-{fac.id:06d}"
        db.add(Pago(factura_id=fac.id, **pago))
        db.add_all(cals)


def _predicciones(db, lote):
    """Predicción de la IA al crear cada pedido (con el modelo vigente) + tiempo real."""
    preds = []
    for r in lote:
        ped = r["pedido"]
        if r["minutos"] is None:
            continue
        local = r["local"]
        res = predecir_tiempo_espera(
            hora=local.hour, dia_semana=local.weekday(), mesas_ocupadas=r["carga"],
            total_items=sum(c for _, c in r["items"]), total_pedido=float(ped.total), db=None, guardar=False,
            carga_de_cocina=True)
        pr = Prediccion(
            hora=local.hour, dia_semana=local.weekday(), mesas_ocupadas=r["carga"],
            total_items=sum(c for _, c in r["items"]), total_pedido=float(ped.total),
            minutos_estimados=res["minutos_estimados"], rango_min=res["rango_min"], rango_max=res["rango_max"],
            nivel_ocupacion=res["nivel_ocupacion"], recomendacion=res["recomendacion"],
            confianza=res["confianza"], version_modelo=res["version_modelo"], fuente=res["fuente"],
            restaurante_id=ped.restaurante_id, pedido_id=ped.id,
            tiempo_real_minutos=round(r["minutos"], 2), creado_en=ped.creado_en)
        preds.append((ped, pr))
    db.add_all([p for _, p in preds])
    db.flush()
    for ped, pr in preds:
        ped.prediccion_id = pr.id
        ped.minutos_estimados = pr.minutos_estimados


def _generar_tramo(db, rng, restaurantes, clientes, emails, desde_dia, hasta_dia, con_predicciones, ahora):
    total_pedidos = 0
    dia = desde_dia
    while dia <= hasta_dia:
        for rest in restaurantes:
            lote = _pedidos_de_dia(rng, rest, rest["productos"], rest["mesas"], clientes, dia, ahora - timedelta(hours=1),
                                   EstadoPedido.entregado)
            if not lote:
                continue
            db.add_all([r["pedido"] for r in lote])
            db.flush()
            if con_predicciones:
                _predicciones(db, lote)
            _cobrar_y_calificar(db, rng, lote, rest["nombre"], rest["efecto"], emails, ahora)
            total_pedidos += len(lote)
        db.commit()
        dia += timedelta(days=1)
    return total_pedidos


def generar(db, dias: int = 60, semilla: int = 2026) -> None:
    ya = db.query(Usuario).filter(Usuario.email.like(f"%{DOMINIO}")).first()
    if ya is not None:
        print("⚠️  Ya hay datos simulados. Ejecuta primero:  python -m app.core.seed_historial --borrar")
        return

    rng = np.random.default_rng(semilla)
    random.seed(semilla)

    restaurantes = []
    for r in db.query(Restaurante).filter(Restaurante.activo.is_(True)).order_by(Restaurante.id).all():
        productos = db.query(Producto).filter(Producto.restaurante_id == r.id, Producto.activo.is_(True)).all()
        if not productos:
            print(f"   ⚠️  {r.nombre}: sin platos propios, se omite")
            continue
        mesas = [m.id for m in db.query(Mesa).filter(Mesa.restaurante_id == r.id, Mesa.activa.is_(True)).all()]
        if not mesas:
            print(f"   ⚠️  {r.nombre}: sin mesas propias, se omite")
            continue
        restaurantes.append({
            "id": r.id, "nombre": r.nombre, "productos": productos, "mesas": mesas,
            "escala": float(rng.uniform(0.85, 1.2)),
            "efecto": {p.id: float(rng.choice([0, 0, 0, 0, 0.4, 0.9])) for p in productos},
        })
    if not restaurantes:
        print("❌ No hay restaurantes con platos y mesas. Corre antes: python -m app.core.seed_restaurantes")
        return

    clientes = _clientes(db)
    emails = {u.id: u.email for u in db.query(Usuario).filter(Usuario.id.in_(clientes)).all()}
    ahora = _utc_ahora()
    hoy_local = hora_local(ahora).date()
    inicio = hoy_local - timedelta(days=dias)
    corte = hoy_local - timedelta(days=DIAS_HOLDOUT)

    print(f"📅 Generando {dias} días de historial para {len(restaurantes)} restaurante(s)…")
    n1 = _generar_tramo(db, rng, restaurantes, clientes, emails, inicio, corte - timedelta(days=1), False, ahora)
    print(f"   · Tramo antiguo: {n1} pedidos")

    print("🧠 Entrenando el modelo con ese historial (sin ver los últimos días)…")
    r = entrenar_modelo(db, motivo="manual")
    print(f"   · Versión {r['version']}: {r['muestras_reales']} pedidos reales, error {r['mae_minutos']} min "
          f"(promediar daría {r['mae_baseline_minutos']} min)")

    n2 = _generar_tramo(db, rng, restaurantes, clientes, emails, corte, hoy_local, True, ahora)
    print(f"   · Últimos {DIAS_HOLDOUT} días: {n2} pedidos, cada uno con la predicción que hizo la IA")

    r = entrenar_modelo(db, motivo="manual")
    print(f"🧠 Versión final {r['version']} activa: {r['muestras_reales']} pedidos reales, error {r['mae_minutos']} min")

    print("\n✅ Listo. Resumen:")
    print(f"   Pedidos: {db.query(Pedido).filter(Pedido.usuario_id.in_(clientes)).count()}")
    print(f"   Facturas: {db.query(Factura).filter(Factura.usuario_id.in_(clientes)).count()}")
    print(f"   Calificaciones: {db.query(Calificacion).filter(Calificacion.usuario_id.in_(clientes)).count()}")
    print("   (datos SIMULADOS · para quitarlos: python -m app.core.seed_historial --borrar)")


def main():
    ap = argparse.ArgumentParser(description="Historial simulado de WaitLess")
    ap.add_argument("--dias", type=int, default=60)
    ap.add_argument("--borrar", action="store_true")
    ap.add_argument("--semilla", type=int, default=2026)
    a = ap.parse_args()
    import app.main  # noqa: F401  (carga TODOS los modelos para que las tablas se creen bien)
    Base.metadata.create_all(bind=engine)
    asegurar_columnas(engine)
    db = SessionLocal()
    try:
        if a.borrar:
            borrar(db)
        else:
            generar(db, a.dias, a.semilla)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        print(f"❌ Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
