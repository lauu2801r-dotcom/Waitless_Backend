"""
Pruebas del flujo de domicilio: sin mesa, dirección/teléfono obligatorios, costo de envío,
pedido mínimo, horario, domicilio desactivado y que la mesa NO se ocupe.
    python tests/test_domicilio.py        (desde la carpeta del backend)
"""
import os, sys, tempfile
from datetime import timedelta

_DB = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ.update(DATABASE_URL=f"sqlite:///{_DB}", SECRET_KEY="x" * 32,
                  MAIL_USERNAME="a", MAIL_PASSWORD="b", MAIL_FROM="a@b.co")
sys.path.insert(0, os.getcwd())

from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.core.security import create_access_token, get_password_hash
from app.modules.auth.models import Restaurante, RolUsuario, Usuario
from app.modules.mesas.models import Mesa, EstadoMesa
from app.modules.menu.models import Producto
from app.modules.restaurantes import horarios as H

db = SessionLocal()
def mk(email, rol):
    u = Usuario(nombre="Ana", apellido="Paz", email=email, hashed_password=get_password_hash("Abcdefg1"),
                rol=rol, verificado=True, activo=True)
    db.add(u); db.commit(); db.refresh(u)
    return u, {"Authorization": "Bearer " + create_access_token({"sub": str(u.id), "email": email, "rol": rol.value})}

ua, ha = mk("a@x.co", RolUsuario.administrador); uc, hc = mk("c@x.co", RolUsuario.cliente)
ra = Restaurante(nombre="Casa Solera", codigo_negocio="A", administrador_id=ua.id)
db.add(ra); db.commit()
mesa = Mesa(numero=1, restaurante_id=ra.id, capacidad=4); db.add(mesa)
p1 = Producto(nombre="Bandeja", precio=30000, restaurante_id=ra.id)
db.add_all([p1]); db.commit()
client = TestClient(app)
ok = fail = 0
def chk(n, c, extra=""):
    global ok, fail
    if c: ok += 1; print("  ok  ", n)
    else: fail += 1; print("  FALLA", n, extra)

def dom(**kw):
    body = {"items": [{"producto_id": p1.id, "cantidad": 2}], "tipo_entrega": "domicilio",
            "direccion_domicilio": "Calle 45 # 12-30, Chapinero", "telefono_contacto": "300 123 4567"}
    body.update(kw)
    return client.post("/pedidos/", headers=hc, json=body)

# ── Validaciones ──
chk("domicilio sin dirección → 422", dom(direccion_domicilio="").status_code == 422)
chk("dirección muy corta → 422", dom(direccion_domicilio="cll 1").status_code == 422)
chk("domicilio sin teléfono → 422", dom(telefono_contacto="").status_code == 422)
chk("teléfono con letras → 422", dom(telefono_contacto="abcdefgh").status_code == 422)
r = client.post("/pedidos/", headers=hc, json={"items": [{"producto_id": p1.id, "cantidad": 1}]})
chk("en restaurante sin mesa → 422", r.status_code == 422, r.text)

# ── Domicilio correcto ──
r = dom(indicaciones_domicilio="Torre 2, apto 301. Timbre malo, llamar.")
d = r.json()
chk("crea domicilio sin mesa", r.status_code == 200 and d["mesa_id"] is None and d["tipo_entrega"] == "domicilio", r.text)
chk("envío por defecto $5.000 sumado al total", d.get("costo_envio") == 5000 and d["total"] == 65000, r.text)
chk("guarda dirección, teléfono e indicaciones", d["direccion_domicilio"].startswith("Calle 45") and d["telefono_contacto"] == "300 123 4567"
    and d["indicaciones_domicilio"].startswith("Torre 2"), r.text)
db.expire_all()
chk("la mesa NO se ocupa", db.query(Mesa).first().estado == EstadoMesa.libre)
pid = d["id"]
r = client.get(f"/pedidos/{pid}", headers=hc)
chk("se lee el pedido (mesa nula, tipo domicilio)", r.status_code == 200 and r.json()["tipo_entrega"] == "domicilio", r.text)
r = client.get("/pedidos/activos", headers=ha)
chk("el restaurante lo ve en activos", r.status_code == 200 and any(x["id"] == pid for x in r.json()), r.text)
for est in ("en_preparacion", "listo", "entregado"):
    r = client.patch(f"/pedidos/{pid}", headers=ha, json={"estado": est})
    chk(f"estado {est} sin mesa", r.status_code == 200 and r.json()["estado"] == est, r.text)
db.expire_all()
chk("entregar domicilio no toca mesas", db.query(Mesa).first().estado == EstadoMesa.libre)

# ── Editar items conserva tipo y envío ──
r = dom(); pid2 = r.json()["id"]
r = client.put(f"/pedidos/{pid2}/items", headers=hc, json={"items": [{"producto_id": p1.id, "cantidad": 1}]})
chk("editar items: sigue domicilio y suma envío", r.status_code == 200 and r.json()["tipo_entrega"] == "domicilio"
    and r.json()["total"] == 35000 and r.json()["mesa_id"] is None, r.text)

# ── En restaurante sigue igual ──
r = client.post("/pedidos/", headers=hc, json={"mesa_id": mesa.id, "items": [{"producto_id": p1.id, "cantidad": 1}]})
chk("pedido en restaurante ok, total sin envío", r.status_code == 200 and r.json()["total"] == 30000 and r.json()["costo_envio"] == 0, r.text)
db.expire_all()
chk("en restaurante la mesa se ocupa", db.query(Mesa).first().estado == EstadoMesa.ocupada)

# ── Configuración del restaurante ──
r = client.patch("/restaurantes/mi-restaurante/datos", headers=ha,
                 json={"costo_domicilio": 8000, "pedido_minimo_domicilio": 100000})
chk("admin configura envío y mínimo", r.status_code == 200 and r.json()["costo_domicilio"] == 8000
    and r.json()["pedido_minimo_domicilio"] == 100000, r.text)
r = dom()
chk("bajo el mínimo → 400 con faltante", r.status_code == 400 and "mínimo" in r.json()["detail"] and "$40.000" in r.json()["detail"], r.text)
r = dom(items=[{"producto_id": p1.id, "cantidad": 4}])
chk("sobre el mínimo con envío $8.000", r.status_code == 200 and r.json()["total"] == 128000, r.text)
chk("envío negativo → 422", client.patch("/restaurantes/mi-restaurante/datos", headers=ha, json={"costo_domicilio": -1}).status_code == 422)
client.patch("/restaurantes/mi-restaurante/datos", headers=ha, json={"pedido_minimo_domicilio": 0})

# ── Domicilio desactivado ──
client.patch("/restaurantes/mi-restaurante/datos", headers=ha, json={"domicilio_activo": False})
r = dom()
chk("domicilio desactivado → 400", r.status_code == 400 and "no tiene servicio" in r.json()["detail"], r.text)
chk("la lista pública lo informa", client.get(f"/restaurantes/{ra.id}").json()["domicilio_activo"] is False)
client.patch("/restaurantes/mi-restaurante/datos", headers=ha, json={"domicilio_activo": True})

# ── Horario ──
ahora = H.ahora_colombia()
dias = {d: None for d in H.DIAS}
r = client.patch("/restaurantes/mi-restaurante/datos", headers=ha, json={"horarios": {"semana": dias}})
chk("guarda horario cerrado", r.status_code == 200, r.text)
r = dom()
chk("restaurante cerrado → 400", r.status_code == 400 and "cerrado" in r.json()["detail"].lower(), r.text)
dias = {d: {"abre": "00:00", "cierra": "23:59"} for d in H.DIAS}
client.patch("/restaurantes/mi-restaurante/datos", headers=ha, json={"horarios": {"semana": dias}})
chk("abierto → vuelve a funcionar", dom().status_code == 200)

# ── Reportes y notificaciones con pedidos sin mesa ──
r = client.get("/reportes/dashboard", headers=ha)
chk("dashboard tolera domicilios", r.status_code == 200, r.text[:200])
r = client.get("/notificaciones/", headers=hc)
chk("notificaciones dicen Domicilio", r.status_code == 200 and any("Domicilio" in (n.get("mensaje") or n.get("detalle") or "") for n in r.json()), r.text[:300])

print(f"\n{ok} ok, {fail} fallas")
sys.exit(1 if fail else 0)
