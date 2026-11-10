"""
Pruebas de exportación de reportes (CSV y PDF) — aislamiento por restaurante.
    python tests/test_reportes_exportar.py        (desde la carpeta del backend)
"""
import os, sys, tempfile
from datetime import datetime, timedelta

_DB = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ.update(DATABASE_URL=f"sqlite:///{_DB}", SECRET_KEY="x" * 32,
                  MAIL_USERNAME="a", MAIL_PASSWORD="b", MAIL_FROM="a@b.co")
sys.path.insert(0, os.getcwd())

from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.core.security import create_access_token, get_password_hash
from app.modules.auth.models import Restaurante, RolUsuario, Usuario
from app.modules.calificaciones.models import Calificacion
from app.modules.inventario.models import Insumo, Proveedor
from app.modules.mesas.models import Mesa
from app.modules.menu.models import Producto
from app.modules.pagos.models import EstadoFactura, Factura, MetodoPago
from app.modules.pedidos.models import EstadoPedido, ItemPedido, Pedido

db = SessionLocal()
def mk(email, rol):
    u = Usuario(nombre="Ana", apellido="Paz", email=email, hashed_password=get_password_hash("Abcdefg1"),
                rol=rol, verificado=True, activo=True)
    db.add(u); db.commit(); db.refresh(u)
    return u, {"Authorization": "Bearer " + create_access_token({"sub": str(u.id), "email": email, "rol": rol.value})}

ua, ha = mk("a@x.co", RolUsuario.administrador); ub, hb = mk("b@x.co", RolUsuario.administrador)
uz, hz = mk("z@x.co", RolUsuario.administrador); uc, hc = mk("c@x.co", RolUsuario.cliente)
ra = Restaurante(nombre="Casa Solera", codigo_negocio="A", administrador_id=ua.id)
rb = Restaurante(nombre="Corona", codigo_negocio="B", administrador_id=ub.id)
db.add_all([ra, rb]); db.commit()

AHORA = datetime.utcnow()
def venta(rest, mesa_n, plato, monto, metodo=MetodoPago.efectivo, anulada=False, dias_atras=0, nombre_cliente="x@x.co"):
    mesa = Mesa(numero=mesa_n, restaurante_id=rest.id, capacidad=4); db.add(mesa); db.commit()
    prod = db.query(Producto).filter_by(nombre=plato, restaurante_id=rest.id).first()
    if not prod:
        prod = Producto(nombre=plato, precio=monto, restaurante_id=rest.id); db.add(prod); db.commit()
    ped = Pedido(usuario_id=uc.id, mesa_id=mesa.id, restaurante_id=rest.id, estado=EstadoPedido.entregado,
                 total=monto, creado_en=AHORA - timedelta(days=dias_atras)); db.add(ped); db.commit()
    db.add(ItemPedido(pedido_id=ped.id, producto_id=prod.id, cantidad=2, precio_unitario=monto/2, subtotal=monto))
    f = Factura(pedido_id=ped.id, usuario_id=uc.id, subtotal=monto, impuesto_pct=8, impuesto=monto*0.08, propina=1000,
                total=monto*1.08+1000, metodo=metodo, estado=EstadoFactura.anulada if anulada else EstadoFactura.pagada,
                pagado_en=AHORA - timedelta(days=dias_atras),
                detalle='{"concepto":"=HYPERLINK(\\"http://malo\\")","cliente_email":"%s","items":[]}' % nombre_cliente)
    db.add(f); db.commit(); f.numero = f"F-{f.id:06d}"; db.commit()
    return ped, prod

p1, prod_pizza = venta(ra, 1, "Pizza", 50000)
venta(ra, 2, "Pizza", 30000, MetodoPago.tarjeta)
venta(ra, 3, "Pasta", 20000, anulada=True)
venta(ra, 4, "Pasta", 10000, dias_atras=40)         # fuera del rango reciente
venta(rb, 1, "Sushi", 99000)                         # OTRO restaurante
db.add_all([
    Calificacion(usuario_id=uc.id, pedido_id=p1.id, producto_id=prod_pizza.id, restaurante_id=ra.id, estrellas=5, comentario="=1+1 rico"),
    Calificacion(usuario_id=uc.id, pedido_id=p1.id, producto_id=prod_pizza.id + 100, restaurante_id=rb.id, estrellas=1, comentario="B malo"),
])
db.add_all([Insumo(restaurante_id=ra.id, nombre="Harina", unidad="kg", stock_actual=2, stock_minimo=5, costo_unitario=3000),
            Insumo(restaurante_id=rb.id, nombre="Salmón", unidad="kg", stock_actual=9, stock_minimo=1, costo_unitario=40000)])
try: db.commit()
except Exception: db.rollback()   # la calificación de B apunta a un producto inexistente en SQLite: se ignora

ok = fail = 0
def check(n, c):
    global ok, fail
    print(("PASS " if c else "FAIL ") + n); ok += bool(c); fail += (not c)

def test_todo():
    with TestClient(app) as c:
        r = c.get("/reportes/ventas.csv", headers=ha)
        txt = r.content.decode("utf-8-sig")
        check("ventas.csv 200 y tipo csv", r.status_code == 200 and "text/csv" in r.headers["content-type"])
        check("viene como descarga", "attachment" in r.headers["content-disposition"] and ".csv" in r.headers["content-disposition"])
        check("trae BOM para Excel", r.content[:3] == b"\xef\xbb\xbf")
        check("separador ; y encabezado", txt.splitlines()[0].startswith("factura;fecha;pedido;cliente;metodo_pago"))
        check("solo 4 ventas de A (incluye anulada y la antigua)", len(txt.strip().splitlines()) == 1 + 4)
        check("no aparece nada del otro restaurante", "99000" not in txt and "Sushi" not in txt)
        check("fórmula neutralizada (=HYPERLINK)", "'=HYPERLINK" in txt and ";=HYPERLINK" not in txt)
        check("decimales con coma", "50000,00" in txt)
        # filtro de fechas
        hoy = (datetime.utcnow() - timedelta(hours=5)).date().isoformat()
        r = c.get(f"/reportes/ventas.csv?desde={hoy}&hasta={hoy}", headers=ha)
        check("filtro por fecha: solo las de hoy (3)", len(r.content.decode("utf-8-sig").strip().splitlines()) == 1 + 3)
        check("desde > hasta -> 400", c.get("/reportes/ventas.csv?desde=2026-12-01&hasta=2026-01-01", headers=ha).status_code == 400)
        # B solo ve lo suyo
        tb = c.get("/reportes/ventas.csv", headers=hb).content.decode("utf-8-sig")
        check("B solo ve su venta", len(tb.strip().splitlines()) == 2 and "99000,00" in tb and "50000,00" not in tb)
        # inventario
        ti = c.get("/reportes/inventario.csv", headers=ha).content.decode("utf-8-sig")
        check("inventario de A: Harina sí, Salmón no", "Harina" in ti and "Salm" not in ti and ";bajo;" in ti)
        # calificaciones
        tc = c.get("/reportes/calificaciones.csv", headers=ha).content.decode("utf-8-sig")
        check("calificaciones de A con fórmula neutralizada", "'=1+1 rico" in tc and "B malo" not in tc)
        # PDF
        r = c.get("/reportes/resumen.pdf", headers=ha)
        check("resumen.pdf es un PDF válido", r.status_code == 200 and r.content[:5] == b"%PDF-" and len(r.content) > 1500)
        open(os.path.join(tempfile.gettempdir(), "resumen_prueba.pdf"), "wb").write(r.content)
        r = c.get("/reportes/resumen.pdf?desde=2020-01-01&hasta=2020-01-02", headers=hb)
        check("PDF de un periodo sin datos también se genera", r.status_code == 200 and r.content[:5] == b"%PDF-")
        # permisos
        check("cliente no puede exportar (403)", c.get("/reportes/ventas.csv", headers=hc).status_code == 403)
        check("sin token (401)", c.get("/reportes/ventas.csv").status_code == 401)
        check("admin sin restaurante (403)", c.get("/reportes/inventario.csv", headers=hz).status_code == 403)
        check("dashboard sigue funcionando", c.get("/reportes/dashboard", headers=ha).status_code == 200)
    assert fail == 0, f"{fail} pruebas fallaron"

if __name__ == "__main__":
    test_todo()
    print(f"\n{ok} OK, {fail} fallos")
