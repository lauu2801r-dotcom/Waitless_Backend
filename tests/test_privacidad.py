"""
Pruebas de derechos del titular (Ley 1581): acceso a mis datos y eliminación de cuenta.
    python tests/test_privacidad.py        (desde la carpeta del backend)
"""
import json, os, sys, tempfile
from datetime import datetime, timedelta

_DB = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ.update(DATABASE_URL=f"sqlite:///{_DB}", SECRET_KEY="x" * 32,
                  MAIL_USERNAME="a", MAIL_PASSWORD="b", MAIL_FROM="a@b.co")
sys.path.insert(0, os.getcwd())

from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.core.security import create_access_token, get_password_hash
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.auth.models import Restaurante, RolUsuario, Usuario
from app.modules.calificaciones.models import Calificacion
from app.modules.clientes.models import Favorito
from app.modules.mesas.models import EstadoMesa, Mesa
from app.modules.menu.models import Producto
from app.modules.notificaciones.models import Notificacion
from app.modules.pagos.models import EstadoFactura, Factura, MetodoPago
from app.modules.pedidos.models import EstadoPedido, Pedido
from app.modules.reservas.models import EstadoReserva, Reserva

db = SessionLocal()
def mk(email, rol, nombre="Ana"):
    u = Usuario(nombre=nombre, apellido="Paz", email=email, telefono="3001234567",
                hashed_password=get_password_hash("Abcdefg1"), rol=rol, verificado=True, activo=True)
    db.add(u); db.commit(); db.refresh(u)
    return u, {"Authorization": "Bearer " + create_access_token({"sub": str(u.id), "email": email, "rol": rol.value})}

ua, ha = mk("admin@x.co", RolUsuario.administrador); uc, hc = mk("cli@x.co", RolUsuario.cliente, "Carla")
uo, ho = mk("otro@x.co", RolUsuario.cliente, "Otro")
ra = Restaurante(nombre="Casa Solera", codigo_negocio="A", administrador_id=ua.id); db.add(ra); db.commit()
mesa = Mesa(numero=1, restaurante_id=ra.id, capacidad=4, estado=EstadoMesa.reservada); db.add(mesa); db.commit()
prod = Producto(nombre="Pizza", precio=20000, restaurante_id=ra.id); db.add(prod); db.commit()
fut = datetime.utcnow() + timedelta(days=2)
res = Reserva(usuario_id=uc.id, mesa_id=mesa.id, fecha_hora=fut, numero_personas=2, notas="Alergia a nueces",
              estado=EstadoReserva.confirmada)
ped = Pedido(usuario_id=uc.id, mesa_id=mesa.id, restaurante_id=ra.id, estado=EstadoPedido.entregado, total=40000,
             notas="sin cebolla", direccion_domicilio="Calle 1 # 2-3")
db.add_all([res, ped]); db.commit()
fac = Factura(pedido_id=ped.id, usuario_id=uc.id, subtotal=40000, impuesto_pct=8, impuesto=3200, propina=0, total=43200,
              metodo=MetodoPago.tarjeta, estado=EstadoFactura.pagada, numero="F-000001",
              detalle=json.dumps({"cliente_email": "cli@x.co", "items": [{"n": "Pizza"}]}))
db.add_all([fac, Calificacion(usuario_id=uc.id, pedido_id=ped.id, producto_id=prod.id, restaurante_id=ra.id,
                              estrellas=5, comentario="Me llamo Carla y estuvo rico"),
            Favorito(usuario_id=uc.id, producto_id=prod.id),
            Notificacion(usuario_id=uc.id, tipo="pedido", titulo="Hola"),
            RegistroAuditoria(usuario_id=uc.id, email="cli@x.co", accion="login")])
db.commit()

client = TestClient(app)
ok = fail = 0
def chk(n, c, extra=""):
    global ok, fail
    if c: ok += 1; print("  ok  ", n)
    else: fail += 1; print("  FALLA", n, extra)

# ── Acceso a mis datos ──
r = client.get("/privacidad/mis-datos", headers=hc)
d = r.json()
chk("exporta mis datos", r.status_code == 200 and d["perfil"]["email"] == "cli@x.co" and d["perfil"]["telefono"] == "3001234567", r.text[:200])
chk("incluye reservas, pedidos, facturas, calificaciones y favoritos",
    len(d["reservas"]) == 1 and len(d["pedidos"]) == 1 and d["facturas"][0]["numero"] == "F-000001"
    and d["calificaciones"][0]["comentario"] and d["favoritos"] == ["Pizza"], r.text[:300])
chk("no mezcla datos de otras personas", "otro@x.co" not in r.text)
chk("sin sesión no se puede", client.get("/privacidad/mis-datos").status_code in (401, 403))

# ── Validaciones de la eliminación ──
e = lambda pw, conf, h=hc: client.post("/privacidad/eliminar-cuenta", headers=h, json={"password": pw, "confirmacion": conf})
chk("sin escribir ELIMINAR → 400", e("Abcdefg1", "borrar").status_code == 400)
chk("contraseña incorrecta → 400", e("Mala1234", "ELIMINAR").status_code == 400)
r = e("Abcdefg1", "ELIMINAR", ha)
chk("un administrador no puede eliminarse desde la app → 400", r.status_code == 400 and "restaurante" in r.json()["detail"], r.text)
chk("sin sesión → 401/403", client.post("/privacidad/eliminar-cuenta", json={"password": "x", "confirmacion": "ELIMINAR"}).status_code in (401, 403))
db.expire_all()
chk("tras los rechazos la cuenta sigue intacta", db.get(Usuario, uc.id).email == "cli@x.co" and db.get(Usuario, uc.id).activo)

# ── Eliminación ──
r = e("Abcdefg1", "eliminar")
chk("elimina la cuenta (acepta minúsculas)", r.status_code == 200, r.text)
db.expire_all()
u = db.get(Usuario, uc.id)
chk("cuenta anonimizada e inactiva", u.email == f"eliminado-{uc.id}@anonimo.invalid" and u.nombre == "Usuario"
    and u.telefono is None and u.activo is False)
chk("la reserva vigente quedó cancelada y la mesa libre",
    db.get(Reserva, res.id).estado == EstadoReserva.cancelada and db.get(Mesa, mesa.id).estado == EstadoMesa.libre)
chk("se borraron las notas de la reserva", db.get(Reserva, res.id).notas is None)
chk("se borraron notificaciones y favoritos",
    db.query(Notificacion).filter_by(usuario_id=uc.id).count() == 0 and db.query(Favorito).filter_by(usuario_id=uc.id).count() == 0)
c = db.query(Calificacion).filter_by(usuario_id=uc.id).first()
chk("la calificación conserva las estrellas pero no el comentario", c.estrellas == 5 and c.comentario is None)
p = db.get(Pedido, ped.id)
chk("el pedido se conserva sin dirección ni notas", p.total == 40000 and p.direccion_domicilio is None and p.notas is None)
f = db.get(Factura, fac.id)
chk("la factura se conserva sin el correo del cliente", f.total == 43200 and json.loads(f.detalle)["cliente_email"] is None
    and json.loads(f.detalle)["items"][0]["n"] == "Pizza")
chk("la auditoría ya no muestra el correo real",
    all(a.email != "cli@x.co" for a in db.query(RegistroAuditoria).filter_by(usuario_id=uc.id).all())
    and db.query(RegistroAuditoria).filter_by(accion="cuenta_eliminada").count() == 1)
chk("el token de la cuenta eliminada ya no sirve", client.get("/privacidad/mis-datos", headers=hc).status_code in (401, 403))
r = client.post("/auth/login", json={"email": "cli@x.co", "password": "Abcdefg1"})
chk("no puede iniciar sesión", r.status_code in (400, 401, 403, 404), r.text)
chk("el correo queda libre para registrarse de nuevo", db.query(Usuario).filter_by(email="cli@x.co").count() == 0)
chk("otra persona no se ve afectada", db.get(Usuario, uo.id).email == "otro@x.co" and db.get(Usuario, uo.id).activo)

print(f"\n{ok} ok, {fail} fallas")
sys.exit(1 if fail else 0)
