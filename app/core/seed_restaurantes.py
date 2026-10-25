"""
Prepara el sistema para varios restaurantes. Se ejecuta UNA vez (se puede repetir sin problema):

    python -m app.core.seed_restaurantes

Qué hace:
  1. Agrega las columnas nuevas si faltan (restaurante en platos, mesas y pedidos).
  2. Tu restaurante actual pasa a llamarse "Casa Solera" (cocina tradicional) y se queda
     con todos los platos, mesas y pedidos que ya existían.
  3. Completa el restaurante "Corona" (hamburguesas y comida rápida) con su menú y sus mesas.

IMPORTANTE: Corona debe registrarse ANTES desde la app, como lo haría cualquier restaurante
(registro de administrador con nombre de restaurante "Corona", código de negocio y verificación
por correo). Así la cuenta usa un correo real. Si todavía no está registrado, el seed lo avisa
y solo prepara Casa Solera; después de registrarlo, vuelve a correr el comando.
"""

from app.core.database import Base, SessionLocal, engine
from app.core.migraciones import asegurar_columnas
from app.modules.auth.models import Restaurante, RolUsuario, Usuario  # noqa: F401
from app.modules.mesas.models import EstadoMesa, Mesa
from app.modules.menu.models import Producto
from app.modules.pedidos.models import Pedido

NOMBRE_PRINCIPAL = "Casa Solera"

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

# número, capacidad, ubicación
MESAS_CORONA = [
    (1, 2, "Terraza"), (2, 2, "Terraza"), (3, 4, "Interior"), (4, 4, "Interior"),
    (5, 4, "Interior"), (6, 6, "Salón"), (7, 6, "Salón"), (8, 2, "Barra"),
]


def main():
    Base.metadata.create_all(bind=engine)
    asegurar_columnas(engine)
    db = SessionLocal()
    try:
        # ── 1. Restaurante principal ──
        principal = (
            db.query(Restaurante)
            .filter(~Restaurante.nombre.ilike("corona"))
            .order_by(Restaurante.id)
            .first()
        )
        if principal is None:
            admin = db.query(Usuario).filter(Usuario.rol == RolUsuario.administrador).order_by(Usuario.id).first()
            if admin is None:
                print("❌ No hay ningún administrador. Regístrate primero como administrador en la app.")
                return
            principal = Restaurante(nombre=NOMBRE_PRINCIPAL, codigo_negocio="PRINCIPAL", administrador_id=admin.id)
            db.add(principal)
            db.flush()
        principal.nombre = NOMBRE_PRINCIPAL
        principal.descripcion = "Cocina tradicional y de autor, con ingredientes frescos de la región."
        principal.tipo_cocina = "Cocina tradicional"
        principal.emoji = "🍲"
        principal.activo = True
        db.flush()

        # Todo lo que existía antes pertenece al restaurante principal
        for modelo in (Producto, Mesa, Pedido):
            n = db.query(modelo).filter(modelo.restaurante_id.is_(None)).update(
                {modelo.restaurante_id: principal.id}, synchronize_session=False
            )
            if n:
                print(f"   · {n} registros de {modelo.__tablename__} asignados a {NOMBRE_PRINCIPAL}")

        # ── 2. Corona ──
        corona = db.query(Restaurante).filter(Restaurante.nombre.ilike("corona")).first()
        if corona is None:
            db.commit()
            print("⚠️  Corona todavía no está registrado.")
            print("    Regístralo desde la app: Registrarme > Administrador > nombre del restaurante \"Corona\",")
            print("    con un correo real y el código de negocio. Luego vuelve a correr este comando.")
            print("✅ Casa Solera lista.")
            return
        corona.nombre = "Corona"
        corona.descripcion = "Hamburguesas artesanales, perros calientes y comida rápida."
        corona.tipo_cocina = "Hamburguesas y comida rápida"
        corona.emoji = "🍔"
        corona.activo = True
        db.flush()

        if db.query(Producto).filter(Producto.restaurante_id == corona.id).count() == 0:
            for nombre, desc, precio, cat in MENU_CORONA:
                db.add(Producto(nombre=nombre, descripcion=desc, precio=precio, categoria=cat,
                                disponible=True, activo=True, restaurante_id=corona.id))
            print(f"   · {len(MENU_CORONA)} platos creados para Corona")

        if db.query(Mesa).filter(Mesa.restaurante_id == corona.id).count() == 0:
            for numero, cap, ubic in MESAS_CORONA:
                db.add(Mesa(numero=numero, capacidad=cap, ubicacion=ubic, estado=EstadoMesa.libre,
                            activa=True, restaurante_id=corona.id))
            print(f"   · {len(MESAS_CORONA)} mesas creadas para Corona")

        db.commit()
        print("✅ Restaurantes listos: Casa Solera y Corona.")
    except Exception as e:  # noqa: BLE001
        db.rollback()
        print(f"❌ Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
