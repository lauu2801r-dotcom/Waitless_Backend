from app.core.database import SessionLocal
from app.modules.mesas.models import Mesa, EstadoMesa

def seed_mesas():
    db = SessionLocal()
    try:
        # Solo crea si no existen
        if db.query(Mesa).count() > 0:
            print("✅ Las mesas ya existen, seed omitido.")
            return

        mesas = [
            Mesa(numero=1,  capacidad=2, ubicacion="Terraza",  estado=EstadoMesa.libre, activa=True),
            Mesa(numero=2,  capacidad=2, ubicacion="Terraza",  estado=EstadoMesa.libre, activa=True),
            Mesa(numero=3,  capacidad=4, ubicacion="Interior", estado=EstadoMesa.libre, activa=True),
            Mesa(numero=4,  capacidad=4, ubicacion="Interior", estado=EstadoMesa.libre, activa=True),
            Mesa(numero=5,  capacidad=4, ubicacion="Interior", estado=EstadoMesa.libre, activa=True),
            Mesa(numero=6,  capacidad=6, ubicacion="Salón",    estado=EstadoMesa.libre, activa=True),
            Mesa(numero=7,  capacidad=6, ubicacion="Salón",    estado=EstadoMesa.libre, activa=True),
            Mesa(numero=8,  capacidad=8, ubicacion="Salón",    estado=EstadoMesa.libre, activa=True),
            Mesa(numero=9,  capacidad=2, ubicacion="Barra",    estado=EstadoMesa.libre, activa=True),
            Mesa(numero=10, capacidad=2, ubicacion="Barra",    estado=EstadoMesa.libre, activa=True),
        ]

        db.add_all(mesas)
        db.commit()
        print(f"✅ {len(mesas)} mesas creadas exitosamente.")
    except Exception as e:
        print(f"❌ Error en seed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_mesas()