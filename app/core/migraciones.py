"""
Migraciones mínimas y seguras.

El proyecto usa Base.metadata.create_all(), que CREA tablas nuevas pero NO
agrega columnas a tablas que ya existen. Esta función agrega, solo si faltan,
las columnas nuevas (se puede ejecutar todas las veces que se quiera).
Para un proyecto más grande se recomienda Alembic.
"""
import logging

from sqlalchemy import inspect, text

logger = logging.getLogger("waitless.migraciones")

# (tabla, columna, definición SQL)
COLUMNAS_NUEVAS = [
    ("restaurantes", "descripcion", "VARCHAR(255)"),
    ("restaurantes", "tipo_cocina", "VARCHAR(100)"),
    ("restaurantes", "emoji", "VARCHAR(10)"),
    ("restaurantes", "activo", "BOOLEAN NOT NULL DEFAULT TRUE"),
    ("productos", "restaurante_id", "INTEGER REFERENCES restaurantes(id)"),
    ("mesas", "restaurante_id", "INTEGER REFERENCES restaurantes(id)"),
    ("pedidos", "restaurante_id", "INTEGER REFERENCES restaurantes(id)"),
    ("usuarios", "restaurante_id", "INTEGER REFERENCES restaurantes(id)"),
    ("usuarios", "cargo", "VARCHAR(30)"),
    # ── IA: ciclo cerrado predicción ↔ tiempo real ──
    ("pedidos", "listo_en", "TIMESTAMP"),
    ("pedidos", "minutos_estimados", "INTEGER"),
    ("pedidos", "prediccion_id", "INTEGER"),
    ("predicciones", "restaurante_id", "INTEGER"),
    ("predicciones", "confianza", "INTEGER"),
    ("predicciones", "version_modelo", "INTEGER"),
    ("predicciones", "fuente", "VARCHAR(10)"),
    ("modelos_ia", "error_p80", "DOUBLE PRECISION"),
]


def asegurar_columnas(engine) -> None:
    insp = inspect(engine)
    tablas = set(insp.get_table_names())
    with engine.begin() as conn:
        for tabla, columna, definicion in COLUMNAS_NUEVAS:
            if tabla not in tablas:
                continue
            existentes = {c["name"] for c in insp.get_columns(tabla)}
            if columna in existentes:
                continue
            conn.execute(text(f'ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}'))
            logger.warning("Columna agregada: %s.%s", tabla, columna)

    _numero_de_mesa_por_restaurante(engine)


def _numero_de_mesa_por_restaurante(engine) -> None:
    """
    Antes el número de mesa era único en todo el sistema. Ahora cada
    restaurante tiene sus propias mesas (Mesa 1 de Corona y Mesa 1 de otro
    restaurante). Solo aplica en PostgreSQL (en SQLite las bases nuevas ya
    nacen con la regla correcta).
    """
    if engine.dialect.name != "postgresql":
        return
    try:
        insp = inspect(engine)
        if "mesas" not in insp.get_table_names():
            return
        with engine.begin() as conn:
            for uc in insp.get_unique_constraints("mesas"):
                if uc["column_names"] == ["numero"]:
                    conn.execute(text(f'ALTER TABLE mesas DROP CONSTRAINT "{uc["name"]}"'))
                    logger.warning("Quitada restricción única global de mesas.numero")
            for ix in insp.get_indexes("mesas"):
                if ix.get("unique") and ix["column_names"] == ["numero"]:
                    conn.execute(text(f'DROP INDEX IF EXISTS "{ix["name"]}"'))
            nombres = {u["name"] for u in inspect(engine).get_unique_constraints("mesas")}
            if "uq_mesa_restaurante_numero" not in nombres:
                conn.execute(text(
                    "ALTER TABLE mesas ADD CONSTRAINT uq_mesa_restaurante_numero "
                    "UNIQUE (restaurante_id, numero)"
                ))
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo ajustar la restricción de mesas: %s", e)
