"""
Exportación de reportes del administrador (CSV y PDF).

Todo se calcula SOLO con los datos del restaurante del administrador.
Las fechas que recibe el usuario son fechas de Colombia (UTC-5); en la base
los datos están en UTC, por eso se convierten al filtrar y al mostrar.
"""
import csv
import io
from datetime import date, datetime, time, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.auth.models import Restaurante
from app.modules.calificaciones.models import Calificacion
from app.modules.inventario.models import Insumo
from app.modules.menu.models import Producto
from app.modules.pagos.models import EstadoFactura, Factura
from app.modules.pedidos.models import EstadoPedido, ItemPedido, Pedido

UTC_MENOS_5 = timedelta(hours=5)
SEPARADOR = ";"   # Excel en español (Colombia) separa columnas con punto y coma


# ───────────────────────── utilidades ─────────────────────────
def rango_utc(
    desde: Optional[date], hasta: Optional[date]
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Fechas de Colombia (incluyendo ambos días) → rango en UTC [inicio, fin)."""
    ini = datetime.combine(desde, time.min) + UTC_MENOS_5 if desde else None
    fin = datetime.combine(hasta, time.min) + timedelta(days=1) + UTC_MENOS_5 if hasta else None
    return ini, fin


def _local(dt: Optional[datetime]) -> str:
    return (dt - UTC_MENOS_5).strftime("%Y-%m-%d %H:%M") if dt else ""


def _seguro(valor) -> str:
    """Evita 'inyección de fórmulas' en Excel: un texto que empieza con = + - @ se neutraliza."""
    if valor is None:
        return ""
    s = str(valor)
    if s and s[0] in "=+-@\t\r":
        return "'" + s
    return s


def _num(x) -> str:
    """Número con 2 decimales y coma decimal (como lo espera Excel en español)."""
    return f"{float(x or 0):.2f}".replace(".", ",")


def _csv(encabezado: List[str], filas: List[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=SEPARADOR, lineterminator="\r\n")
    w.writerow(encabezado)
    w.writerows(filas)
    # BOM para que Excel respete tildes y eñes
    return ("﻿" + buf.getvalue()).encode("utf-8")


def _facturas_de(db: Session, rid: int, desde: Optional[date], hasta: Optional[date]):
    ini, fin = rango_utc(desde, hasta)
    q = (
        db.query(Factura)
        .join(Pedido, Pedido.id == Factura.pedido_id)
        .filter(Pedido.restaurante_id == rid)
    )
    if ini:
        q = q.filter(Factura.pagado_en >= ini)
    if fin:
        q = q.filter(Factura.pagado_en < fin)
    return q.order_by(Factura.pagado_en, Factura.id).all()


# ───────────────────────── CSV ─────────────────────────
def ventas_csv(db: Session, rid: int, desde: Optional[date], hasta: Optional[date]) -> bytes:
    filas = []
    for f in _facturas_de(db, rid, desde, hasta):
        filas.append([
            f.numero, _local(f.pagado_en), f.pedido_id, _seguro(f.cliente_email),
            f.metodo.value, _num(f.subtotal), _num(f.impuesto), _num(f.propina),
            _num(f.total), f.estado.value, _seguro(f.concepto),
        ])
    return _csv(
        ["factura", "fecha", "pedido", "cliente", "metodo_pago", "subtotal",
         "impuesto", "propina", "total", "estado", "concepto"],
        filas,
    )


def inventario_csv(db: Session, rid: int) -> bytes:
    insumos = (
        db.query(Insumo)
        .filter(Insumo.restaurante_id == rid, Insumo.activo == True)  # noqa: E712
        .order_by(Insumo.categoria, Insumo.nombre).all()
    )
    filas = [[
        _seguro(i.nombre), _seguro(i.categoria), i.unidad, _num(i.stock_actual),
        _num(i.stock_minimo), i.estado, _num(i.costo_unitario), _num(i.valor),
        _seguro(i.proveedor_nombre),
    ] for i in insumos]
    return _csv(
        ["insumo", "categoria", "unidad", "stock_actual", "stock_minimo", "estado",
         "costo_unitario", "valor_en_stock", "proveedor"],
        filas,
    )


def calificaciones_csv(db: Session, rid: int, desde: Optional[date], hasta: Optional[date]) -> bytes:
    ini, fin = rango_utc(desde, hasta)
    q = db.query(Calificacion).filter(Calificacion.restaurante_id == rid)
    if ini:
        q = q.filter(Calificacion.creado_en >= ini)
    if fin:
        q = q.filter(Calificacion.creado_en < fin)
    filas = [[
        _local(c.creado_en), _seguro(c.producto.nombre if c.producto else ""),
        c.estrellas, _seguro(c.comentario),
        _seguro(c.usuario.nombre if c.usuario else ""),
    ] for c in q.order_by(Calificacion.creado_en, Calificacion.id).all()]
    return _csv(["fecha", "plato", "estrellas", "comentario", "cliente"], filas)


# ───────────────────────── PDF resumen ─────────────────────────
def _cop(x: float) -> str:
    return "$" + f"{round(float(x or 0)):,}".replace(",", ".")


def datos_resumen(db: Session, rid: int, desde: Optional[date], hasta: Optional[date]) -> dict:
    ini, fin = rango_utc(desde, hasta)
    rest = db.query(Restaurante).filter(Restaurante.id == rid).first()

    pagadas = [f for f in _facturas_de(db, rid, desde, hasta) if f.estado == EstadoFactura.pagada]
    total = sum(f.total for f in pagadas)
    por_metodo = {}
    for f in pagadas:
        por_metodo[f.metodo.value] = por_metodo.get(f.metodo.value, 0.0) + f.total

    # pedidos por estado
    qp = db.query(Pedido.estado, func.count(Pedido.id)).filter(Pedido.restaurante_id == rid)
    if ini:
        qp = qp.filter(Pedido.creado_en >= ini)
    if fin:
        qp = qp.filter(Pedido.creado_en < fin)
    pedidos = {e.value: n for e, n in qp.group_by(Pedido.estado).all()}

    # platos más vendidos (pedidos entregados)
    qt = (
        db.query(Producto.nombre, func.sum(ItemPedido.cantidad), func.sum(ItemPedido.subtotal))
        .join(ItemPedido, ItemPedido.producto_id == Producto.id)
        .join(Pedido, Pedido.id == ItemPedido.pedido_id)
        .filter(Pedido.restaurante_id == rid, Pedido.estado == EstadoPedido.entregado)
    )
    if ini:
        qt = qt.filter(Pedido.creado_en >= ini)
    if fin:
        qt = qt.filter(Pedido.creado_en < fin)
    top = [
        (n, int(c or 0), float(s or 0))
        for n, c, s in qt.group_by(Producto.id, Producto.nombre)
        .order_by(func.sum(ItemPedido.cantidad).desc()).limit(5).all()
    ]

    # calificaciones
    qc = db.query(func.avg(Calificacion.estrellas), func.count(Calificacion.id)).filter(
        Calificacion.restaurante_id == rid
    )
    if ini:
        qc = qc.filter(Calificacion.creado_en >= ini)
    if fin:
        qc = qc.filter(Calificacion.creado_en < fin)
    prom, n_cal = qc.one()

    # inventario
    insumos = db.query(Insumo).filter(Insumo.restaurante_id == rid, Insumo.activo == True).all()  # noqa: E712
    criticos = sorted(
        [i for i in insumos if i.estado in ("bajo", "agotado")],
        key=lambda i: (i.estado != "agotado", i.nombre),
    )

    return {
        "restaurante": rest.nombre if rest else "Restaurante",
        "desde": desde, "hasta": hasta,
        "n_facturas": len(pagadas), "total_ventas": total,
        "ticket_promedio": (total / len(pagadas)) if pagadas else 0.0,
        "propinas": sum(f.propina for f in pagadas),
        "por_metodo": por_metodo, "pedidos": pedidos, "top": top,
        "cal_promedio": float(prom) if prom is not None else None, "cal_total": int(n_cal or 0),
        "n_insumos": len(insumos), "valor_inventario": sum(i.valor for i in insumos),
        "criticos": criticos[:15], "n_criticos": len(criticos),
    }


def resumen_pdf(db: Session, rid: int, desde: Optional[date], hasta: Optional[date]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    d = datos_resumen(db, rid, desde, hasta)
    cafe, terracota, crema = colors.HexColor("#3D2817"), colors.HexColor("#C65D3A"), colors.HexColor("#FBF7F0")
    est = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=est["Title"], textColor=cafe, fontSize=22, leading=28, alignment=0, spaceAfter=6)
    h2 = ParagraphStyle("h2", parent=est["Heading2"], textColor=terracota, fontSize=13, spaceBefore=14, spaceAfter=6)
    normal = ParagraphStyle("n", parent=est["Normal"], textColor=cafe, fontSize=10)
    peq = ParagraphStyle("p", parent=normal, fontSize=8.5, textColor=colors.HexColor("#8B6F4E"))

    def periodo():
        if desde and hasta:
            return f"{desde:%d/%m/%Y} al {hasta:%d/%m/%Y}"
        if desde:
            return f"desde el {desde:%d/%m/%Y}"
        if hasta:
            return f"hasta el {hasta:%d/%m/%Y}"
        return "todo el historial"

    def tabla(filas, anchos, encabezado=True):
        t = Table(filas, colWidths=anchos, repeatRows=1 if encabezado else 0, hAlign="LEFT")
        estilo = [
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("TEXTCOLOR", (0, 0), (-1, -1), cafe),
            ("ROWBACKGROUNDS", (0, 1 if encabezado else 0), (-1, -1), [colors.white, crema]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E8DDD0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]
        if encabezado:
            estilo += [("BACKGROUND", (0, 0), (-1, 0), cafe), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                       ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
        t.setStyle(TableStyle(estilo))
        return t

    ahora_co = datetime.utcnow() - UTC_MENOS_5
    el = [
        Paragraph(f"Reporte de {d['restaurante']}", h1),
        Paragraph(f"Periodo: {periodo()} · Generado el {ahora_co:%d/%m/%Y %H:%M}", peq),
        Paragraph("Ventas", h2),
        tabla([
            ["Ventas (facturas pagadas)", "Facturas", "Ticket promedio", "Propinas"],
            [_cop(d["total_ventas"]), str(d["n_facturas"]), _cop(d["ticket_promedio"]), _cop(d["propinas"])],
        ], [5.2 * cm, 3 * cm, 4.2 * cm, 4 * cm]),
    ]
    if d["por_metodo"]:
        el += [Spacer(1, 8), tabla(
            [["Método de pago", "Total"]] + [[m.capitalize(), _cop(v)] for m, v in sorted(d["por_metodo"].items(), key=lambda x: -x[1])],
            [8 * cm, 6 * cm])]

    el.append(Paragraph("Pedidos", h2))
    if d["pedidos"]:
        el.append(tabla([["Estado", "Cantidad"]] + [[k.replace("_", " ").capitalize(), str(v)] for k, v in d["pedidos"].items()], [8 * cm, 6 * cm]))
    else:
        el.append(Paragraph("Sin pedidos en el periodo.", normal))

    el.append(Paragraph("Platos más vendidos", h2))
    if d["top"]:
        el.append(tabla([["Plato", "Unidades", "Ingresos"]] + [[n, str(c), _cop(s)] for n, c, s in d["top"]], [8 * cm, 3 * cm, 4 * cm]))
    else:
        el.append(Paragraph("Sin ventas entregadas en el periodo.", normal))

    el.append(Paragraph("Calificaciones", h2))
    if d["cal_total"]:
        el.append(Paragraph(f"Promedio {d['cal_promedio']:.2f} de 5 estrellas, sobre {d['cal_total']} calificación(es).", normal))
    else:
        el.append(Paragraph("Sin calificaciones en el periodo.", normal))

    el.append(Paragraph("Inventario (estado actual)", h2))
    el.append(Paragraph(
        f"{d['n_insumos']} insumo(s) activo(s) · valor en bodega {_cop(d['valor_inventario'])} · "
        f"{d['n_criticos']} bajo el mínimo o agotado(s).", normal))
    if d["criticos"]:
        el += [Spacer(1, 6), tabla(
            [["Insumo", "Stock", "Mínimo", "Estado"]] + [
                [i.nombre, f"{i.stock_actual:g} {i.unidad}", f"{i.stock_minimo:g}", i.estado.capitalize()]
                for i in d["criticos"]],
            [6.5 * cm, 3.5 * cm, 3 * cm, 3 * cm])]

    el += [Spacer(1, 18), Paragraph(
        "Reporte generado por WaitLess. Los pagos y parte del historial pueden ser simulados "
        "(prototipo académico).", peq)]

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                      topMargin=2 * cm, bottomMargin=2 * cm,
                      title=f"Reporte {d['restaurante']}", author="WaitLess").build(el)
    return buf.getvalue()
