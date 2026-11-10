"""
Carga datos de ejemplo de inventario (los mismos de la pantalla de diseño).
Cada restaurante tiene su propio inventario: el script crea el de ejemplo
para cada restaurante que todavía no tenga insumos. Se puede ejecutar varias
veces sin duplicar nada:

    python -m app.core.seed_inventario
"""
from app.core.database import Base, SessionLocal, engine
from app.modules.auth.models import Restaurante, Usuario  # noqa: F401  (necesario para las FK)
from app.modules.compras import models as _compras  # noqa: F401
from app.modules.inventario.models import (
    Insumo, MovimientoInventario, Proveedor, TipoMovimiento,
)

PROVEEDORES = [
    "Molinos del Sur", "Plaza de Mercado", "Lácteos Andinos", "Frigorífico Central",
    "Avícola Nacional", "Cervecería Local", "Bodega del Valle",
    "Distribuidora H2O", "Papelería Express", "Importadora Mediterránea",
]

# nombre, categoría, stock, mínimo, unidad, emoji, proveedor, costo unitario (COP)
INSUMOS = [
    ("Harina de trigo", "Ingredientes", 12.5, 15, "kg", "🌾", "Molinos del Sur", 3200),
    ("Tomate fresco", "Ingredientes", 8, 10, "kg", "🍅", "Plaza de Mercado", 4500),
    ("Queso mozzarella", "Ingredientes", 5.2, 8, "kg", "🧀", "Lácteos Andinos", 28000),
    ("Carne de res", "Ingredientes", 22, 12, "kg", "🥩", "Frigorífico Central", 32000),
    ("Pollo", "Ingredientes", 0, 10, "kg", "🍗", "Avícola Nacional", 12000),
    ("Cerveza artesanal", "Bebidas", 48, 24, "botellas", "🍺", "Cervecería Local", 6500),
    ("Vino tinto reserva", "Bebidas", 18, 12, "botellas", "🍷", "Bodega del Valle", 45000),
    ("Agua mineral", "Bebidas", 6, 20, "botellas", "💧", "Distribuidora H2O", 2000),
    ("Servilletas", "Insumos", 450, 200, "unidades", "🧻", "Papelería Express", 60),
    ("Aceite de oliva", "Ingredientes", 9.5, 5, "litros", "🫒", "Importadora Mediterránea", 38000),
]


def seed_restaurante(db, restaurante_id: int) -> bool:
    """Crea el inventario de ejemplo de UN restaurante (si todavía no tiene)."""
    if db.query(Insumo).filter(Insumo.restaurante_id == restaurante_id).count() > 0:
        return False
    provs = {}
    for nombre in PROVEEDORES:
        p = Proveedor(nombre=nombre, restaurante_id=restaurante_id)
        db.add(p)
        db.flush()
        provs[nombre] = p
    for nombre, cat, stock, minimo, unidad, emoji, prov, costo in INSUMOS:
        i = Insumo(nombre=nombre, categoria=cat, unidad=unidad, emoji=emoji,
                   stock_actual=stock, stock_minimo=minimo, costo_unitario=costo,
                   proveedor_id=provs[prov].id, restaurante_id=restaurante_id)
        db.add(i)
        db.flush()
        if stock > 0:
            db.add(MovimientoInventario(
                insumo_id=i.id, tipo=TipoMovimiento.entrada, cantidad=stock,
                motivo="Stock inicial (datos de ejemplo)",
                stock_anterior=0, stock_resultante=stock,
            ))
    return True


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        restaurantes = db.query(Restaurante).order_by(Restaurante.id).all()
        if not restaurantes:
            print("No hay restaurantes todavía: crea uno y vuelve a ejecutar.")
            return
        for r in restaurantes:
            if seed_restaurante(db, r.id):
                print(f"{r.nombre}: {len(PROVEEDORES)} proveedores y {len(INSUMOS)} insumos creados.")
            else:
                print(f"{r.nombre}: ya tiene inventario, no se hace nada.")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
