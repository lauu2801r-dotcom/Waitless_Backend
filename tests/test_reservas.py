"""
Pruebas de reservas: crear, modificar, cancelar con motivo, avisos y aislamiento por restaurante.
    python tests/test_reservas.py        (desde la carpeta del backend)
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
from app.modules.mesas.models import EstadoMesa, Mesa
from app.modules.notificaciones.models import Notificacion
from app.modules.reservas.models import Reserva
from app.websocket.manager import manager

db = SessionLocal()
eventos = []
manager.emitir = lambda sala, ev: eventos.append((sala, ev))  # captura los avisos en vivo

def mk(email, rol, rest_id=None):
    u = Usuario(nombre="Ana", apellido="Paz", email=email, hashed_password=get_password_hash("Abcdefg1"),
                rol=rol, verificado=True, activo=True, restaurante_id=rest_id)
    db.add(u); db.commit(); db.refresh(u)
    return u, {"Authorization": "Bearer " + create_access_token({"sub": str(u.id), "email": email, "rol": rol.value})}

ua, ha = mk("a@x.co", RolUsuario.administrador); ub, hb = mk("b@x.co", RolUsuario.administrador)
c1, h1 = mk("c1@x.co", RolUsuario.cliente); c2, h2 = mk("c2@x.co", RolUsuario.cliente)
ra = Restaurante(nombre="Casa Solera", codigo_negocio="A", administrador_id=ua.id)
rb = Restaurante(nombre="Corona", codigo_negocio="B", administrador_id=ub.id)
db.add_all([ra, rb]); db.commit()
ue, he = mk("e@x.co", RolUsuario.empleado, ra.id)
ma = [Mesa(numero=n, restaurante_id=ra.id, capacidad=4) for n in (1, 2, 3)]
mb = Mesa(numero=1, restaurante_id=rb.id, capacidad=4)
db.add_all(ma + [mb]); db.commit()

client = TestClient(app)
ok = fail = 0
def chk(nombre, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print("  ok  ", nombre)
    else: fail += 1; print("  FALLA", nombre, extra)

def cuando(horas=24): return (datetime.utcnow() - timedelta(hours=5) + timedelta(hours=horas)).isoformat()
def nuevas(uid): return db.query(Notificacion).filter(Notificacion.usuario_id == uid).count()

# ── Crear ──
r = client.post("/reservas/", headers=h1, json={"mesa_id": ma[0].id, "fecha_hora": cuando(), "numero_personas": 2})
chk("crear reserva", r.status_code == 200, r.text)
rid = r.json()["id"]
chk("respuesta trae mesa_numero y restaurante_id", r.json()["mesa_numero"] == 1 and r.json()["restaurante_id"] == ra.id)
chk("el admin del restaurante recibe aviso de nueva reserva", nuevas(ua.id) == 1)
chk("el empleado del restaurante recibe aviso", nuevas(ue.id) == 1)
chk("el admin de OTRO restaurante no recibe nada", nuevas(ub.id) == 0)
chk("el cliente recibe su aviso", nuevas(c1.id) == 1)
chk("evento en vivo para el cliente", any(s == f"usuario:{c1.id}" and e.get("tipo") == "reserva_estado" for s, e in eventos))
r = client.post("/reservas/", headers=h2, json={"mesa_id": ma[0].id, "fecha_hora": cuando(), "numero_personas": 2})
chk("mesa ya reservada → 400", r.status_code == 400)
r = client.post("/reservas/", headers=h2, json={"mesa_id": ma[1].id, "fecha_hora": cuando(-5), "numero_personas": 2})
chk("fecha pasada → 400", r.status_code == 400 and "futura" in r.json()["detail"], r.text)
r = client.post("/reservas/", headers=h2, json={"mesa_id": ma[1].id, "fecha_hora": cuando(), "numero_personas": 9})
chk("más personas que la capacidad → 400", r.status_code == 400)
r = client.post("/reservas/", headers=h2, json={"mesa_id": ma[1].id, "fecha_hora": cuando(), "numero_personas": 0})
chk("0 personas → 422", r.status_code == 422)

# ── Modificar ──
r = client.patch(f"/reservas/{rid}", headers=h1, json={"numero_personas": 3, "notas": "Cumpleaños"})
chk("cliente modifica personas y notas", r.status_code == 200 and r.json()["numero_personas"] == 3 and r.json()["notas"] == "Cumpleaños", r.text)
r = client.patch(f"/reservas/{rid}", headers=h1, json={"numero_personas": 9})
chk("modificar a más de la capacidad → 400", r.status_code == 400)
r = client.patch(f"/reservas/{rid}", headers=h1, json={"fecha_hora": cuando(-3)})
chk("modificar a fecha pasada → 400", r.status_code == 400)
r = client.patch(f"/reservas/{rid}", headers=h1, json={"estado": "completada"})
chk("el cliente NO puede cambiar el estado → 403", r.status_code == 403)
r = client.patch(f"/reservas/{rid}", headers=h2, json={"notas": "hack"})
chk("otro cliente no puede modificarla → 403", r.status_code == 403)
r = client.patch(f"/reservas/{rid}", headers=hb, json={"notas": "hack"})
chk("admin de otro restaurante no puede → 403", r.status_code == 403)
before = nuevas(ua.id)
client.patch(f"/reservas/{rid}", headers=h1, json={"notas": "Cumple 2"})
chk("al modificar se avisa al restaurante", nuevas(ua.id) == before + 1)
r = client.patch(f"/reservas/{rid}", headers=he, json={"estado": "confirmada"})
chk("empleado confirma la reserva", r.status_code == 200 and r.json()["estado"] == "confirmada", r.text)
chk("el cliente ve el estado en vivo", any(s == f"usuario:{c1.id}" and e.get("estado") == "confirmada" for s, e in eventos))
r = client.patch(f"/reservas/{rid}", headers=he, json={"estado": "cancelada"})
chk("cancelar por PATCH no se permite → 400", r.status_code == 400)

# ── Listados / aislamiento ──
r = client.get("/reservas/todas", headers=ha)
chk("admin A ve su reserva", r.status_code == 200 and [x["id"] for x in r.json()] == [rid])
r = client.get("/reservas/todas", headers=hb)
chk("admin B NO ve reservas del restaurante A", r.status_code == 200 and r.json() == [])
chk("cliente no accede a /todas → 403", client.get("/reservas/todas", headers=h1).status_code == 403)
chk("otro cliente no ve la reserva → 403", client.get(f"/reservas/{rid}", headers=h2).status_code == 403)
chk("admin de otro restaurante no ve la reserva → 403", client.get(f"/reservas/{rid}", headers=hb).status_code == 403)
chk("mis-reservas del dueño", [x["id"] for x in client.get("/reservas/mis-reservas", headers=h1).json()] == [rid])

# ── Cancelar con motivo ──
a0, c0 = nuevas(ua.id), nuevas(c1.id)
r = client.delete(f"/reservas/{rid}", headers=h2)
chk("otro cliente no puede cancelar → 403", r.status_code == 403)
r = client.delete(f"/reservas/{rid}", headers=h1, params={"motivo": "Me surgió un imprevisto"})
chk("cliente cancela con motivo", r.status_code == 200 and r.json()["motivo"] == "Me surgió un imprevisto", r.text)
db.expire_all()
chk("la mesa queda libre", db.get(Mesa, ma[0].id).estado == EstadoMesa.libre)
chk("el motivo queda guardado", db.get(Reserva, rid).motivo_cancelacion == "Me surgió un imprevisto")
chk("se avisa al restaurante con el motivo", nuevas(ua.id) == a0 + 1 and
    "imprevisto" in db.query(Notificacion).filter_by(usuario_id=ua.id).order_by(Notificacion.id.desc()).first().detalle)
chk("el cliente recibe su aviso de cancelación", nuevas(c1.id) == c0 + 1)
chk("reserva cancelada aparece con estado y motivo", client.get(f"/reservas/{rid}", headers=h1).json()["estado"] == "cancelada")
chk("cancelar otra vez → 400", client.delete(f"/reservas/{rid}", headers=h1).status_code == 400)
chk("no se puede modificar una cancelada → 400", client.patch(f"/reservas/{rid}", headers=h1, json={"notas": "x"}).status_code == 400)

# ── Cancela el restaurante → avisa al cliente; no libera mesa ocupada ──
r = client.post("/reservas/", headers=h2, json={"mesa_id": ma[2].id, "fecha_hora": cuando(), "numero_personas": 2})
rid2 = r.json()["id"]
c20 = nuevas(c2.id)
r = client.delete(f"/reservas/{rid2}", headers=he, params={"motivo": "Cerramos por evento privado"})
chk("empleado cancela con motivo", r.status_code == 200, r.text)
chk("el cliente recibe el motivo", nuevas(c2.id) == c20 + 1 and
    "evento privado" in db.query(Notificacion).filter_by(usuario_id=c2.id).order_by(Notificacion.id.desc()).first().detalle)
r = client.post("/reservas/", headers=h2, json={"mesa_id": ma[2].id, "fecha_hora": cuando(), "numero_personas": 2})
rid3 = r.json()["id"]
m = db.get(Mesa, ma[2].id); m.estado = EstadoMesa.ocupada; db.commit()
client.delete(f"/reservas/{rid3}", headers=h2)
db.expire_all()
chk("cancelar NO libera una mesa ya ocupada", db.get(Mesa, ma[2].id).estado == EstadoMesa.ocupada)
r = client.delete(f"/reservas/{rid3}", headers=h2, params={"motivo": "x" * 300})
chk("motivo > 255 → 422", r.status_code == 422)

# ── Avisos al personal: pedidos, pagos y reseñas ──
from app.modules.calificaciones.models import Calificacion
from app.modules.menu.models import Producto
from app.modules.notificaciones import service as nsvc
from app.modules.pedidos.models import EstadoPedido, ItemPedido, Pedido

chk("la reserva trae el nombre del cliente", client.get("/reservas/todas", headers=ha).json()[0]["cliente_nombre"] == "Ana Paz")
a0, e0, b0 = nuevas(ua.id), nuevas(ue.id), nuevas(ub.id)
prod = Producto(nombre="Pizza", precio=20000, restaurante_id=ra.id); db.add(prod); db.commit()
ped = Pedido(usuario_id=c1.id, mesa_id=ma[0].id, restaurante_id=ra.id, estado=EstadoPedido.entregado, total=40000)
db.add(ped); db.commit()
db.add(ItemPedido(pedido_id=ped.id, producto_id=prod.id, cantidad=2, precio_unitario=20000, subtotal=40000)); db.commit()
nsvc.avisar_pedido_al_restaurante(db, ped)
chk("nuevo pedido avisa al admin y al empleado, no a otro restaurante",
    nuevas(ua.id) == a0 + 1 and nuevas(ue.id) == e0 + 1 and nuevas(ub.id) == b0)
class _F:  # factura mínima
    numero = "F-000001"; total = 43000
nsvc.avisar_pago_al_restaurante(db, ped.id, _F())
chk("pago recibido avisa al personal", nuevas(ua.id) == a0 + 2)
db.add(Calificacion(usuario_id=c1.id, pedido_id=ped.id, producto_id=prod.id, restaurante_id=ra.id, estrellas=4, comentario="Rico")); db.commit()
nsvc.avisar_resena_al_restaurante(db, ped.id)
ult = db.query(Notificacion).filter_by(usuario_id=ua.id).order_by(Notificacion.id.desc()).first()
chk("reseña nueva avisa con promedio y comentario", ult.titulo == "Nueva reseña" and "4.0/5" in ult.detalle and "Rico" in ult.detalle, ult.detalle)
r = client.get("/notificaciones/", headers=ha)
chk("el admin ve sus notificaciones por la API", r.status_code == 200 and len(r.json()) >= 3, r.text[:100])

print(f"\n{ok} ok, {fail} fallas")
sys.exit(1 if fail else 0)
