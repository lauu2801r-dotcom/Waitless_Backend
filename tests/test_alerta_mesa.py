"""
Pruebas HU-004: alerta de mesa ocupada demasiado tiempo.
    python tests/test_alerta_mesa.py        (desde la carpeta del backend)
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
from app.modules.mesas import alertas
from app.modules.mesas.models import EstadoMesa, Mesa
from app.modules.notificaciones.models import Notificacion
from app.websocket.manager import manager

db = SessionLocal()
eventos = []
manager.emitir = lambda sala, ev: eventos.append((sala, ev))

def mk(email, rol, rest_id=None):
    u = Usuario(nombre="Ana", apellido="Paz", email=email, hashed_password=get_password_hash("Abcdefg1"),
                rol=rol, verificado=True, activo=True, restaurante_id=rest_id)
    db.add(u); db.commit(); db.refresh(u)
    return u, {"Authorization": "Bearer " + create_access_token({"sub": str(u.id), "email": email, "rol": rol.value})}

ua, ha = mk("a@x.co", RolUsuario.administrador); ub, hb = mk("b@x.co", RolUsuario.administrador)
ra = Restaurante(nombre="Casa Solera", codigo_negocio="A", administrador_id=ua.id)
rb = Restaurante(nombre="Corona", codigo_negocio="B", administrador_id=ub.id)
db.add_all([ra, rb]); db.commit()
ue, he = mk("e@x.co", RolUsuario.empleado, ra.id)
m1 = Mesa(numero=1, restaurante_id=ra.id, capacidad=4); m2 = Mesa(numero=2, restaurante_id=ra.id, capacidad=4)
mb = Mesa(numero=1, restaurante_id=rb.id, capacidad=4)
db.add_all([m1, m2, mb]); db.commit()
client = TestClient(app)
ok = fail = 0
def chk(n, c, extra=""):
    global ok, fail
    if c: ok += 1; print("  ok  ", n)
    else: fail += 1; print("  FALLA", n, extra)
def avisos(uid): return db.query(Notificacion).filter_by(usuario_id=uid, tipo="mesa").count()
def atras(mesa, minutos):
    db.expire_all(); m = db.get(Mesa, mesa.id); m.ocupada_desde = datetime.utcnow() - timedelta(minutes=minutos); db.commit()

# ── ocupada_desde se controla solo ──
r = client.patch(f"/mesas/{m1.id}/estado", headers=he, params={"estado": "ocupada"})
chk("al ocupar la mesa se guarda desde cuándo", r.status_code == 200 and r.json()["minutos_ocupada"] == 0 and r.json()["alerta_tiempo"] is False, r.text)
db.expire_all()
chk("ocupada_desde quedó registrada", db.get(Mesa, m1.id).ocupada_desde is not None)
r = client.patch(f"/mesas/{m2.id}/estado", headers=ha, params={"estado": "reservada"})
chk("una mesa que no está ocupada no cuenta tiempo", r.json()["minutos_ocupada"] is None)

# ── Revisión ──
chk("antes de tiempo no se avisa", alertas.revisar(db) == 0 and avisos(ua.id) == 0)
atras(m1, 60)
chk("a los 60 min (límite 90) todavía no", alertas.revisar(db) == 0)
atras(m1, 95)
n = alertas.revisar(db)
chk("a los 95 min se envía 1 alerta", n == 1, str(n))
chk("la alerta llega al admin y al empleado del restaurante", avisos(ua.id) == 1 and avisos(ue.id) == 1)
chk("no llega al admin de otro restaurante", avisos(ub.id) == 0)
txt = db.query(Notificacion).filter_by(usuario_id=ua.id, tipo="mesa").first()
chk("el mensaje dice mesa y minutos", "Mesa 1" in txt.titulo and "95" in txt.titulo, txt.titulo)
chk("se emitió el evento en vivo", any(e.get("tipo") == "mesa_alerta" for _, e in eventos))
chk("la segunda revisión NO repite la alerta", alertas.revisar(db) == 0 and avisos(ua.id) == 1)
r = client.get("/mesas/", headers=ha)
fila = [x for x in r.json() if x["id"] == m1.id][0]
chk("la API marca la mesa con alerta y los minutos", fila["alerta_tiempo"] is True and fila["minutos_ocupada"] >= 95, str(fila))

# ── Liberar y volver a ocupar reinicia la cuenta ──
client.patch(f"/mesas/{m1.id}/estado", headers=he, params={"estado": "libre"})
db.expire_all(); m = db.get(Mesa, m1.id)
chk("al liberar se limpia el contador y la alerta", m.ocupada_desde is None and m.alerta_tiempo_enviada is False)
client.patch(f"/mesas/{m1.id}/estado", headers=he, params={"estado": "ocupada"})
atras(m1, 100)
chk("al ocupar de nuevo se vuelve a avisar", alertas.revisar(db) == 1 and avisos(ua.id) == 2)

# ── Umbral por restaurante ──
r = client.patch("/restaurantes/mi-restaurante/datos", headers=ha, json={"minutos_alerta_mesa": 30})
chk("el admin cambia el tiempo máximo a 30 min", r.status_code == 200 and r.json()["minutos_alerta_mesa"] == 30, r.text)
chk("menos de 15 min no se acepta", client.patch("/restaurantes/mi-restaurante/datos", headers=ha, json={"minutos_alerta_mesa": 5}).status_code == 422)
chk("más de 480 min no se acepta", client.patch("/restaurantes/mi-restaurante/datos", headers=ha, json={"minutos_alerta_mesa": 900}).status_code == 422)
client.patch(f"/mesas/{m2.id}/estado", headers=he, params={"estado": "ocupada"})
atras(m2, 40)
chk("con límite de 30 min, 40 min ya alerta", alertas.revisar(db) == 1)
db.expire_all(); db.get(Mesa, mb.id).estado = EstadoMesa.ocupada; db.commit()
atras(mb, 40)
chk("el otro restaurante sigue con 90 min (40 no alerta)", alertas.revisar(db) == 0)
r = client.get("/restaurantes/mi-restaurante/datos", headers=ha)
chk("el valor por defecto es 90", client.get(f"/restaurantes/{rb.id}").json()["minutos_alerta_mesa"] == 90)

# ── Mesas ya ocupadas antes de existir la función ──
db.expire_all(); m = db.get(Mesa, mb.id); m.ocupada_desde = None; db.commit()
alertas.revisar(db)
db.expire_all()
chk("ocupada sin fecha: se empieza a contar desde ahora", db.get(Mesa, mb.id).ocupada_desde is not None)

print(f"\n{ok} ok, {fail} fallas")
sys.exit(1 if fail else 0)
