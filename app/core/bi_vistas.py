"""
WaitLess — Vistas SQL para Power BI
====================================
Crea (o recrea) las vistas `bi_*` en la base de datos. Son SOLO LECTURA: no
cambian ninguna tabla, solo ordenan los datos para que Power BI los entienda
(horas en Colombia, nombres de días en español, columnas calculadas…).

Uso (desde la carpeta Waitless_Backend, con el .venv activado):

    python -m app.core.bi_vistas                     # crea / actualiza las vistas
    python -m app.core.bi_vistas --rol-bi "ClaveSegura123"
                                                     # además crea un usuario SOLO LECTURA
                                                     # (waitless_bi) para conectar Power BI
    python -m app.core.bi_vistas --borrar            # quita las vistas (y el rol si existe)

Todas las vistas incluyen `es_simulado` = TRUE para los datos que creó
`seed_historial` (clientes @demo.waitless), así en Power BI se pueden separar
de los pedidos reales con un filtro.
"""
import argparse
import re
import sys

from sqlalchemy import text

from app.core.database import engine

ROL_BI = "waitless_bi"

# Las fechas se guardan en UTC sin zona → se convierten a hora de Colombia.
def _local(col: str) -> str:
    return f"({col} AT TIME ZONE 'UTC' AT TIME ZONE 'America/Bogota')"


_DIA = """CASE EXTRACT(ISODOW FROM {f})::int
        WHEN 1 THEN 'Lunes' WHEN 2 THEN 'Martes' WHEN 3 THEN 'Miércoles'
        WHEN 4 THEN 'Jueves' WHEN 5 THEN 'Viernes' WHEN 6 THEN 'Sábado'
        ELSE 'Domingo' END"""

_MES = """CASE EXTRACT(MONTH FROM {f})::int
        WHEN 1 THEN 'Enero' WHEN 2 THEN 'Febrero' WHEN 3 THEN 'Marzo' WHEN 4 THEN 'Abril'
        WHEN 5 THEN 'Mayo' WHEN 6 THEN 'Junio' WHEN 7 THEN 'Julio' WHEN 8 THEN 'Agosto'
        WHEN 9 THEN 'Septiembre' WHEN 10 THEN 'Octubre' WHEN 11 THEN 'Noviembre'
        ELSE 'Diciembre' END"""


def dia(f: str) -> str:
    return _DIA.format(f=f)


def mes(f: str) -> str:
    return _MES.format(f=f)


# Orden en que se crean (las que dependen de otra van después).
VISTAS: dict[str, str] = {}

VISTAS["bi_restaurantes"] = """
SELECT r.id                       AS restaurante_id,
       r.nombre                   AS restaurante,
       COALESCE(r.tipo_cocina, 'Sin definir') AS tipo_cocina,
       r.activo                   AS activo
FROM restaurantes r
"""

VISTAS["bi_productos"] = f"""
SELECT p.id                       AS producto_id,
       p.nombre                   AS producto,
       COALESCE(p.categoria, 'Sin categoría') AS categoria,
       p.precio                   AS precio,
       p.restaurante_id           AS restaurante_id,
       r.nombre                   AS restaurante,
       COALESCE(p.disponible, TRUE) AS disponible
FROM productos p
LEFT JOIN restaurantes r ON r.id = p.restaurante_id
WHERE COALESCE(p.activo, TRUE)
"""

# Un renglón por pedido (tabla de hechos principal).
VISTAS["bi_pedidos"] = f"""
SELECT p.id                                   AS pedido_id,
       p.restaurante_id                       AS restaurante_id,
       r.nombre                               AS restaurante,
       p.estado::text                         AS estado,
       p.tipo_entrega::text                   AS tipo_entrega,
       m.numero                               AS mesa,
       p.total                                AS total,
       COALESCE(it.productos, 0)              AS productos,
       {_local('p.creado_en')}                AS fecha_hora,
       CAST({_local('p.creado_en')} AS date)  AS fecha,
       EXTRACT(HOUR FROM {_local('p.creado_en')})::int      AS hora,
       EXTRACT(ISODOW FROM {_local('p.creado_en')})::int    AS dia_semana_num,
       {dia(_local('p.creado_en'))}           AS dia_semana,
       {mes(_local('p.creado_en'))}           AS mes,
       EXTRACT(MONTH FROM {_local('p.creado_en')})::int     AS mes_num,
       EXTRACT(YEAR FROM {_local('p.creado_en')})::int      AS anio,
       p.minutos_estimados                    AS minutos_estimados,
       CASE WHEN p.listo_en IS NOT NULL AND p.creado_en IS NOT NULL
            THEN ROUND((EXTRACT(EPOCH FROM (p.listo_en - p.creado_en)) / 60.0)::numeric, 2)
       END                                    AS minutos_reales,
       (f.pedido_id IS NOT NULL)              AS pagado,
       COALESCE(u.email LIKE '%@demo.waitless', FALSE) AS es_simulado
FROM pedidos p
LEFT JOIN restaurantes r ON r.id = p.restaurante_id
LEFT JOIN mesas m        ON m.id = p.mesa_id
LEFT JOIN usuarios u     ON u.id = p.usuario_id
LEFT JOIN (SELECT pedido_id, SUM(cantidad) AS productos
           FROM items_pedido GROUP BY pedido_id) it ON it.pedido_id = p.id
LEFT JOIN (SELECT DISTINCT pedido_id FROM facturas
           WHERE estado::text = 'pagada') f ON f.pedido_id = p.id
"""

# Un renglón por factura (ventas = facturas pagadas, no anuladas).
VISTAS["bi_ventas"] = f"""
SELECT f.id                                   AS factura_id,
       f.numero                               AS numero,
       f.pedido_id                            AS pedido_id,
       p.restaurante_id                       AS restaurante_id,
       r.nombre                               AS restaurante,
       f.metodo::text                         AS metodo_pago,
       f.estado::text                         AS estado,
       f.subtotal                             AS subtotal,
       f.impuesto                             AS impuesto,
       f.propina                              AS propina,
       f.total                                AS total,
       {_local('f.pagado_en')}                AS fecha_hora,
       CAST({_local('f.pagado_en')} AS date)  AS fecha,
       EXTRACT(HOUR FROM {_local('f.pagado_en')})::int      AS hora,
       EXTRACT(ISODOW FROM {_local('f.pagado_en')})::int    AS dia_semana_num,
       {dia(_local('f.pagado_en'))}           AS dia_semana,
       {mes(_local('f.pagado_en'))}           AS mes,
       EXTRACT(MONTH FROM {_local('f.pagado_en')})::int     AS mes_num,
       EXTRACT(YEAR FROM {_local('f.pagado_en')})::int      AS anio,
       COALESCE(u.email LIKE '%@demo.waitless', FALSE) AS es_simulado
FROM facturas f
JOIN pedidos p           ON p.id = f.pedido_id
LEFT JOIN restaurantes r ON r.id = p.restaurante_id
LEFT JOIN usuarios u     ON u.id = f.usuario_id
"""

# Un renglón por producto vendido dentro de un pedido (no cancelado).
VISTAS["bi_items_vendidos"] = f"""
SELECT i.id                                   AS item_id,
       i.pedido_id                            AS pedido_id,
       p.restaurante_id                       AS restaurante_id,
       r.nombre                               AS restaurante,
       pr.id                                  AS producto_id,
       pr.nombre                              AS producto,
       COALESCE(pr.categoria, 'Sin categoría') AS categoria,
       i.cantidad                             AS cantidad,
       i.precio_unitario                      AS precio_unitario,
       i.subtotal                             AS subtotal,
       CAST({_local('p.creado_en')} AS date)  AS fecha,
       EXTRACT(HOUR FROM {_local('p.creado_en')})::int AS hora,
       COALESCE(u.email LIKE '%@demo.waitless', FALSE) AS es_simulado
FROM items_pedido i
JOIN pedidos p           ON p.id = i.pedido_id
JOIN productos pr        ON pr.id = i.producto_id
LEFT JOIN restaurantes r ON r.id = p.restaurante_id
LEFT JOIN usuarios u     ON u.id = p.usuario_id
WHERE p.estado::text <> 'cancelado'
"""

# Un renglón por predicción de la IA, con su resultado real cuando ya se cerró.
VISTAS["bi_ia_predicciones"] = f"""
SELECT pr.id                                  AS prediccion_id,
       pr.pedido_id                           AS pedido_id,
       pr.restaurante_id                      AS restaurante_id,
       r.nombre                               AS restaurante,
       pr.version_modelo                      AS version_modelo,
       pr.fuente                              AS fuente,
       {_local('pr.creado_en')}               AS fecha_hora,
       CAST({_local('pr.creado_en')} AS date) AS fecha,
       pr.hora                                AS hora,
       pr.dia_semana + 1                      AS dia_semana_num,
       CASE pr.dia_semana WHEN 0 THEN 'Lunes' WHEN 1 THEN 'Martes' WHEN 2 THEN 'Miércoles'
            WHEN 3 THEN 'Jueves' WHEN 4 THEN 'Viernes' WHEN 5 THEN 'Sábado'
            ELSE 'Domingo' END                AS dia_semana,
       pr.mesas_ocupadas                      AS carga_cocina,
       pr.nivel_ocupacion                     AS nivel_carga,
       pr.total_items                         AS productos,
       pr.total_pedido                        AS total_pedido,
       pr.minutos_estimados                   AS minutos_estimados,
       pr.rango_min                           AS rango_min,
       pr.rango_max                           AS rango_max,
       pr.confianza                           AS confianza,
       ROUND(pr.tiempo_real_minutos::numeric, 2) AS minutos_reales,
       (pr.tiempo_real_minutos IS NOT NULL)   AS cerrada,
       CASE WHEN pr.tiempo_real_minutos IS NOT NULL
            THEN ROUND(ABS(pr.minutos_estimados - pr.tiempo_real_minutos)::numeric, 2) END
                                              AS error_absoluto,
       CASE WHEN pr.tiempo_real_minutos IS NOT NULL
            THEN ROUND((pr.minutos_estimados - pr.tiempo_real_minutos)::numeric, 2) END
                                              AS error_con_signo,
       CASE WHEN pr.tiempo_real_minutos IS NULL THEN NULL
            WHEN ABS(pr.minutos_estimados - pr.tiempo_real_minutos) <= 5 THEN 1 ELSE 0 END
                                              AS acierto_5min,
       CASE WHEN pr.tiempo_real_minutos IS NULL THEN NULL
            WHEN ABS(pr.minutos_estimados - pr.tiempo_real_minutos) <= 10 THEN 1 ELSE 0 END
                                              AS acierto_10min,
       CASE WHEN pr.tiempo_real_minutos IS NULL THEN NULL
            WHEN pr.tiempo_real_minutos BETWEEN pr.rango_min AND pr.rango_max THEN 1 ELSE 0 END
                                              AS dentro_del_rango
FROM predicciones pr
LEFT JOIN restaurantes r ON r.id = pr.restaurante_id
"""

# Un renglón por versión entrenada del modelo.
VISTAS["bi_ia_modelos"] = f"""
SELECT m.version                              AS version,
       'v' || m.version::text                 AS version_texto,
       m.algoritmo                            AS algoritmo,
       m.motivo                               AS motivo,
       m.activo                               AS activo,
       {_local('m.entrenado_en')}             AS entrenado_en,
       m.muestras_reales                      AS muestras_reales,
       m.muestras_sinteticas                  AS muestras_arranque,
       m.total_muestras                       AS total_muestras,
       ROUND(m.mae::numeric, 2)               AS error_entrenamiento_min,
       ROUND(m.mae_baseline::numeric, 2)      AS error_si_promediara_min,
       CASE WHEN m.mae_baseline > 0
            THEN ROUND(((1 - m.mae / m.mae_baseline) * 100)::numeric, 1) END
                                              AS mejora_vs_promedio_pct,
       ROUND(m.r2::numeric, 4)                AS r2,
       ROUND(m.error_p80::numeric, 2)         AS error_p80_min
FROM modelos_ia m
"""

VISTAS["bi_calificaciones"] = f"""
SELECT c.id                                   AS calificacion_id,
       c.pedido_id                            AS pedido_id,
       c.restaurante_id                       AS restaurante_id,
       r.nombre                               AS restaurante,
       c.producto_id                          AS producto_id,
       pr.nombre                              AS producto,
       COALESCE(pr.categoria, 'Sin categoría') AS categoria,
       c.estrellas                            AS estrellas,
       c.comentario                           AS comentario,
       CAST({_local('c.creado_en')} AS date)  AS fecha,
       COALESCE(u.email LIKE '%@demo.waitless', FALSE) AS es_simulado
FROM calificaciones c
LEFT JOIN restaurantes r ON r.id = c.restaurante_id
LEFT JOIN productos pr   ON pr.id = c.producto_id
LEFT JOIN usuarios u     ON u.id = c.usuario_id
"""

VISTAS["bi_inventario"] = """
SELECT i.id                                   AS insumo_id,
       i.nombre                               AS insumo,
       i.categoria                            AS categoria,
       i.unidad                               AS unidad,
       i.stock_actual                         AS stock_actual,
       i.stock_minimo                         AS stock_minimo,
       (i.stock_actual <= i.stock_minimo)     AS bajo_el_minimo,
       i.costo_unitario                       AS costo_unitario,
       ROUND((i.stock_actual * i.costo_unitario)::numeric, 2) AS valor_en_stock,
       COALESCE(pv.nombre, 'Sin proveedor')   AS proveedor
FROM insumos i
LEFT JOIN proveedores pv ON pv.id = i.proveedor_id
WHERE i.activo
"""


def _ejecutar(sql: str, **params) -> None:
    with engine.begin() as con:
        con.execute(text(sql), params)


def crear_vistas() -> list[str]:
    creadas = []
    for nombre, cuerpo in VISTAS.items():
        _ejecutar(f"CREATE OR REPLACE VIEW {nombre} AS {cuerpo}")
        creadas.append(nombre)
    return creadas


def borrar_vistas() -> None:
    for nombre in reversed(list(VISTAS)):
        _ejecutar(f"DROP VIEW IF EXISTS {nombre}")


def crear_rol_solo_lectura(clave: str) -> None:
    """Usuario waitless_bi: solo puede LEER las vistas bi_* (nada más)."""
    if len(clave) < 10 or "'" in clave or '"' in clave:
        sys.exit("La clave del rol debe tener 10+ caracteres y no llevar comillas.")
    db = engine.url.database
    with engine.begin() as con:
        existe = con.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ROL_BI}).first()
        verbo = "ALTER" if existe else "CREATE"
        con.execute(text(f"{verbo} ROLE {ROL_BI} LOGIN PASSWORD '{clave}'"))
        con.execute(text(f'GRANT CONNECT ON DATABASE "{db}" TO {ROL_BI}'))
        con.execute(text(f"GRANT USAGE ON SCHEMA public TO {ROL_BI}"))
        con.execute(text(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {ROL_BI}"))
        for nombre in VISTAS:
            con.execute(text(f"GRANT SELECT ON {nombre} TO {ROL_BI}"))


def borrar_rol() -> None:
    with engine.begin() as con:
        if con.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ROL_BI}).first():
            con.execute(text(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {ROL_BI}"))
            con.execute(text(f"DROP OWNED BY {ROL_BI}"))
            con.execute(text(f"DROP ROLE {ROL_BI}"))


def main() -> None:
    ap = argparse.ArgumentParser(description="Vistas SQL para Power BI")
    ap.add_argument("--borrar", action="store_true", help="quita las vistas y el rol de solo lectura")
    ap.add_argument("--rol-bi", metavar="CLAVE", help="crea el usuario de solo lectura waitless_bi")
    args = ap.parse_args()

    if engine.dialect.name != "postgresql":
        sys.exit("Estas vistas son para PostgreSQL (Neon). Revisa DATABASE_URL en tu .env")

    # Importa la app para que SQLAlchemy conozca todas las tablas.
    import app.main  # noqa: F401

    if args.borrar:
        borrar_vistas()
        borrar_rol()
        print("🧹 Vistas bi_* y rol waitless_bi eliminados.")
        return

    for n in crear_vistas():
        with engine.connect() as con:
            filas = con.execute(text(f"SELECT COUNT(*) FROM {n}")).scalar()
        print(f"   ✓ {n:<22} {filas:>7} filas")

    if args.rol_bi:
        crear_rol_solo_lectura(args.rol_bi)
        print(f"\n🔒 Usuario de solo lectura '{ROL_BI}' listo (solo puede leer las vistas bi_*).")

    print("\n✅ Vistas listas. Ahora conéctate desde Power BI Desktop (ver guía).")


if __name__ == "__main__":
    main()
