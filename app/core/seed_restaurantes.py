"""
Prepara el sistema para varios restaurantes. Se puede ejecutar varias veces sin duplicar nada:

    python -m app.core.seed_restaurantes

  · El restaurante "tradicional" (p. ej. Casa Solera) es el que ya tenías: conserva los platos,
    mesas y pedidos que existían antes de manejar varios restaurantes.
  · CORONA (hamburguesas y comida rápida) se registra desde la app como cualquier restaurante
    (correo real + código de negocio + verificación). Este comando le carga su menú de
    hamburguesas y sus mesas.

Si Corona todavía no está registrado, el seed lo avisa; después de registrarlo vuelve a correrlo.
"""
from app.core.database import Base, SessionLocal, engine
from app.core.migraciones import asegurar_columnas
from app.modules.auth.models import Restaurante
from app.modules.mesas.models import EstadoMesa, Mesa
from app.modules.menu.models import Producto
from app.modules.pedidos.models import ItemPedido, Pedido

# nombre, descripción, precio, categoría
MENU_CORONA = [
    ("Corona Clásica", "Carne de res 150 g, queso cheddar, lechuga, tomate y salsa de la casa.", 18900, "Hamburguesas"),
    ("Corona Doble", "Doble carne, doble queso, pepinillos y cebolla caramelizada.", 24900, "Hamburguesas"),
    ("BBQ Bacon", "Carne, tocineta crocante, aros de cebolla y salsa BBQ ahumada.", 26900, "Hamburguesas"),
    ("Pollo Crispy", "Pechuga apanada, lechuga, tomate y mayonesa de ajo.", 21900, "Hamburguesas"),
    ("Veggie Corona", "Medallón de lentejas y quinoa, aguacate y salsa de yogur.", 19900, "Hamburguesas"),
    ("Perro Clásico", "Salchicha americana, queso, papas ripio y salsas.", 12900, "Perros calientes"),
    ("Perro Ranchero", "Salchicha, chorizo, maíz tierno, queso y salsa ranchera.", 15900, "Perros calientes"),
    ("Combo Corona", "Hamburguesa Clásica + papas medianas + gaseosa.", 29900, "Combos"),
    ("Combo Doble", "Hamburguesa Doble + papas grandes + gaseosa.", 36900, "Combos"),
    ("Papas fritas", "Porción grande de papas a la francesa.", 8900, "Acompañantes"),
    ("Aros de cebolla", "Aros apanados con salsa de la casa.", 9900, "Acompañantes"),
    ("Nuggets x8", "Ocho nuggets de pollo con dos salsas.", 11900, "Acompañantes"),
    ("Gaseosa", "Botella 400 ml, sabor a elección.", 4500, "Bebidas"),
    ("Limonada natural", "Jugo de limón recién exprimido.", 6500, "Bebidas"),
    ("Malteada de vainilla", "Helado de vainilla y crema chantilly.", 11900, "Bebidas"),
    ("Brownie con helado", "Brownie tibio con bola de helado de vainilla.", 9900, "Postres"),
]

# número, capacidad, ubicación (mesas nuevas de un restaurante que no tenga)
MESAS = [
    (1, 2, "Terraza"), (2, 2, "Terraza"), (3, 4, "Interior"), (4, 4, "Interior"),
    (5, 4, "Interior"), (6, 6, "Salón"), (7, 6, "Salón"), (8, 2, "Barra"),
]


def main():
    Base.metadata.create_all(bind=engine)
    asegurar_columnas(engine)
    db = SessionLocal()
    try:
        tradicional = (
            db.query(Restaurante).filter(~Restaurante.nombre.ilike("corona%"))
            .order_by(Restaurante.id).first()
        )
        corona = (
            db.query(Restaurante).filter(Restaurante.nombre.ilike("corona%"))
            .order_by(Restaurante.id).first()
        )

        # ── Restaurante tradicional: se queda con lo que ya existía ──
        if tradicional is not None:
            tradicional.descripcion = tradicional.descripcion or "Cocina tradicional y de autor, con ingredientes frescos de la región."
            tradicional.tipo_cocina = tradicional.tipo_cocina or "Cocina tradicional"
            tradicional.emoji = tradicional.emoji or "🍲"
            tradicional.activo = True
            db.flush()
            for modelo in (Producto, Mesa):
                n = db.query(modelo).filter(modelo.restaurante_id.is_(None)).update(
                    {modelo.restaurante_id: tradicional.id}, synchronize_session=False)
                if n:
                    print(f"   · {n} registros de {modelo.__tablename__} asignados a {tradicional.nombre}")
            pendientes = db.query(Pedido).filter(Pedido.restaurante_id.is_(None)).all()
            for p in pendientes:
                item = db.query(ItemPedido).filter(ItemPedido.pedido_id == p.id).first()
                prod = db.query(Producto).filter(Producto.id == item.producto_id).first() if item else None
                p.restaurante_id = (prod.restaurante_id if prod else None) or (p.mesa.restaurante_id if p.mesa else None)
            if pendientes:
                print(f"   · {len(pendientes)} pedidos existentes asignados a su restaurante")
            if db.query(Mesa).filter(Mesa.restaurante_id == tradicional.id).count() == 0:
                for numero, cap, ubic in MESAS:
                    db.add(Mesa(numero=numero, capacidad=cap, ubicacion=ubic, estado=EstadoMesa.libre,
                                activa=True, restaurante_id=tradicional.id))
                print(f"   · {len(MESAS)} mesas creadas para {tradicional.nombre}")

        # ── Corona ──
        if corona is None:
            db.commit()
            print("\n⚠️  Corona todavía no está registrado.")
            print("    Regístralo desde la app (Registrarme > Administrador): nombre del restaurante \"Corona\",")
            print("    un correo real, el código de negocio y verifica el OTP. Luego vuelve a correr este comando.")
            if tradicional is not None:
                print(f"✅ {tradicional.nombre} lista.")
            return

        corona.nombre = "Corona"
        corona.descripcion = corona.descripcion or "Hamburguesas artesanales, perros calientes y comida rápida."
        corona.tipo_cocina = corona.tipo_cocina or "Hamburguesas y comida rápida"
        corona.emoji = corona.emoji or "🍔"
        corona.activo = True
        db.flush()

        if db.query(Producto).filter(Producto.restaurante_id == corona.id).count() == 0:
            for nombre, desc, precio, cat in MENU_CORONA:
                db.add(Producto(nombre=nombre, descripcion=desc, precio=precio, categoria=cat,
                                disponible=True, activo=True, restaurante_id=corona.id))
            print(f"   · {len(MENU_CORONA)} platos creados para Corona")
        if db.query(Mesa).filter(Mesa.restaurante_id == corona.id).count() == 0:
            for numero, cap, ubic in MESAS:
                db.add(Mesa(numero=numero, capacidad=cap, ubicacion=ubic, estado=EstadoMesa.libre,
                            activa=True, restaurante_id=corona.id))
            print(f"   · {len(MESAS)} mesas creadas para Corona")

        db.commit()
        otro = f"{tradicional.nombre} y " if tradicional is not None else ""
        print(f"✅ Restaurantes listos: {otro}Corona.")
    except Exception as e:  # noqa: BLE001
        db.rollback()
        print(f"❌ Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
