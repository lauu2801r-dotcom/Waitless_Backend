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
    # ── Inventario, proveedores y compras: uno por restaurante ──
    ("proveedores", "restaurante_id", "INTEGER REFERENCES restaurantes(id)"),
    ("insumos", "restaurante_id", "INTEGER REFERENCES restaurantes(id)"),
    ("ordenes_compra", "restaurante_id", "INTEGER REFERENCES restaurantes(id)"),
    # ── Reservas: motivo de cancelación ──
    ("reservas", "motivo_cancelacion", "VARCHAR(255)"),
    # ── Perfil del restaurante: contacto, horarios (con días especiales) y galería ──
    ("restaurantes", "direccion", "VARCHAR(200)"),
    ("restaurantes", "telefono", "VARCHAR(30)"),
    ("restaurantes", "instagram", "VARCHAR(100)"),
    ("restaurantes", "horarios", "TEXT"),
    ("restaurantes", "galeria", "TEXT"),
    # ── Mesas: alerta por exceso de tiempo ocupada (HU-004) ──
    ("mesas", "ocupada_desde", "TIMESTAMP"),
    ("mesas", "alerta_tiempo_enviada", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("restaurantes", "minutos_alerta_mesa", "INTEGER"),
    # ── Domicilio: configuración del restaurante y datos del pedido ──
    ("restaurantes", "imagen_url", "VARCHAR(255)"),
    ("restaurantes", "domicilio_activo", "BOOLEAN"),
    ("restaurantes", "costo_domicilio", "INTEGER"),
    ("restaurantes", "pedido_minimo_domicilio", "INTEGER"),
    ("pedidos", "telefono_contacto", "VARCHAR(20)"),
    ("pedidos", "indicaciones_domicilio", "VARCHAR(200)"),
    ("pedidos", "costo_envio", "DOUBLE PRECISION"),
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

    _pedido_sin_mesa(engine)
    _numero_de_mesa_por_restaurante(engine)
    _inventario_por_restaurante(engine)


def _pedido_sin_mesa(engine) -> None:
    """Un pedido a domicilio no tiene mesa: pedidos.mesa_id pasa a aceptar NULL (solo PostgreSQL)."""
    if engine.dialect.name != "postgresql":
        return
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE pedidos ALTER COLUMN mesa_id DROP NOT NULL"))
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo permitir pedidos sin mesa: %s", e)


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


def _unica_por_restaurante(engine, tabla: str, nombre_restriccion: str) -> None:
    """
    Quita la restricción "nombre único en todo el sistema" y crea
    UNIQUE (restaurante_id, nombre): dos restaurantes pueden tener, cada uno,
    su "Harina de trigo". Solo PostgreSQL (en SQLite las bases nuevas ya
    nacen con la regla correcta).
    """
    if engine.dialect.name != "postgresql":
        return
    insp = inspect(engine)
    if tabla not in insp.get_table_names():
        return
    with engine.begin() as conn:
        for uc in insp.get_unique_constraints(tabla):
            if uc["column_names"] == ["nombre"]:
                conn.execute(text(f'ALTER TABLE {tabla} DROP CONSTRAINT "{uc["name"]}"'))
                logger.warning("Quitada restricción única global de %s.nombre", tabla)
        for ix in insp.get_indexes(tabla):
            if ix.get("unique") and ix["column_names"] == ["nombre"]:
                conn.execute(text(f'DROP INDEX IF EXISTS "{ix["name"]}"'))
        nombres = {u["name"] for u in inspect(engine).get_unique_constraints(tabla)}
        if nombre_restriccion not in nombres:
            conn.execute(text(
                f"ALTER TABLE {tabla} ADD CONSTRAINT {nombre_restriccion} "
                "UNIQUE (restaurante_id, nombre)"
            ))


def _inventario_por_restaurante(engine) -> None:
    """
    Antes el inventario, los proveedores y las órdenes de compra eran de todo
    el sistema. Ahora cada restaurante tiene los suyos:
      1. el nombre pasa a ser único POR restaurante;
      2. lo que ya existía (sin dueño) queda asignado al primer restaurante
         creado; los demás pueden cargar su propio inventario de ejemplo con
         `python -m app.core.seed_inventario`.
    Se puede ejecutar todas las veces que se quiera.
    """
    try:
        insp = inspect(engine)
        tablas = set(insp.get_table_names())
        if not {"proveedores", "insumos", "ordenes_compra", "restaurantes"} <= tablas:
            return
        _unica_por_restaurante(engine, "proveedores", "uq_proveedor_restaurante_nombre")
        _unica_por_restaurante(engine, "insumos", "uq_insumo_restaurante_nombre")
        with engine.begin() as conn:
            primero = conn.execute(text("SELECT MIN(id) FROM restaurantes")).scalar()
            if primero is None:
                return
            for tabla in ("proveedores", "insumos"):
                n = conn.execute(
                    text(f"UPDATE {tabla} SET restaurante_id = :r WHERE restaurante_id IS NULL"),
                    {"r": primero},
                ).rowcount
                if n:
                    logger.warning("%s: %s filas sin restaurante asignadas al restaurante %s",
                                   tabla, n, primero)
            # las órdenes heredan el restaurante de su proveedor
            conn.execute(text(
                "UPDATE ordenes_compra SET restaurante_id = "
                "(SELECT p.restaurante_id FROM proveedores p WHERE p.id = ordenes_compra.proveedor_id) "
                "WHERE restaurante_id IS NULL"
            ))
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo separar el inventario por restaurante: %s", e)
