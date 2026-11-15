"""
Pruebas del pago con el portal WaitLess Pay: referencia del portal guardada en el pago,
registro de intentos rechazados (sin factura) e historial de pagos del cliente.
    python tests/test_pagos_portal.py        (desde la carpeta del backend)
"""
import os, sys, tempfile

_DB = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ.update(DATABASE_URL=f"sqlite:///{_DB}", SECRET_KEY="x" * 32,
                  MAIL_USERNAME="a", MAIL_PASSWORD="b", MAIL_FROM="a@b.co")
sys.path.insert(0, os.getcwd())

from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.core.security import create_access_token, get_password_hash
from app.modules.auth.models import Restaurante, RolUsuario, Usuario
from app.modules.mesas.models import Mesa
from app.modules.menu.models import Producto
from app.modules.pagos import service as pagos_service

pagos_service.enviar_factura_email = lambda *a, **k: None   # no enviar correos reales

db = SessionLocal()
def mk(email, rol):
    u = Usuario(nombre="Ana", apellido="Paz", email=email, hashed_password=get_password_hash("Abcdefg1"),
                rol=rol, verificado=True, activo=True)
    db.add(u); db.commit(); db.refresh(u)
    return u, {"Authorization": "Bearer " + create_access_token({"sub": str(u.id), "email": email, "rol": rol.value})}

ua, ha = mk("a@x.co", RolUsuario.administrador)
uc, hc = mk("c@x.co", RolUsuario.cliente)
uo, ho = mk("o@x.co", RolUsuario.cliente)
ra = Restaurante(nombre="Casa Solera", codigo_negocio="A", administrador_id=ua.id)
db.add(ra); db.commit()
mesa = Mesa(numero=1, restaurante_id=ra.id, capacidad=4)
p1 = Producto(nombre="Bandeja", precio=30000, restaurante_id=ra.id)
db.add_all([mesa, p1]); db.commit()
client = TestClient(app)
ok = fail = 0
def chk(n, c, extra=""):
    global ok, fail
    if c: ok += 1; print("  ok  ", n)
    else: fail += 1; print("  FALLA", n, extra)

def pedido(h=None):
    r = client.post("/pedidos/", headers=h or hc, json={"mesa_id": mesa.id, "items": [{"producto_id": p1.id, "cantidad": 1}]})
    assert r.status_code == 200, r.text
    return r.json()["id"]

# ── Rechazo registrado ──
pid = pedido()
r = client.post("/pagos/rechazo", headers=hc, json={"pedido_id": pid, "metodo": "tarjeta", "propina": 1000,
                "referencia": "WLP-ABCD1234", "motivo": "Tarjeta rechazada"})
d = r.json()
chk("registra un pago rechazado", r.status_code == 200 and d["estado"] == "rechazado" and d["factura"] is None, r.text)
chk("guarda la referencia del portal", d["referencia"] == "WLP-ABCD1234", r.text)
chk("guarda el motivo", d["motivo_rechazo"] == "Tarjeta rechazada", r.text)
chk("el monto incluye impuesto y propina", d["monto"] == round(30000 * 1.08 + 1000, 2), str(d["monto"]))
chk("un rechazo no deja el pedido pagado", client.get(f"/pagos/pedido/{pid}", headers=hc).json()[0]["estado"] == "rechazado")
chk("el pedido sigue sin factura", all(f["pedido_id"] != pid for f in client.get("/pagos/mis-facturas", headers=hc).json()))

r = client.post("/pagos/rechazo", headers=hc, json={"pedido_id": pid, "metodo": "tarjeta", "referencia": "hola", "motivo": "x" * 500})
chk("referencia con formato raro se ignora", r.status_code == 200 and r.json()["referencia"] is None, r.text)
chk("el motivo se recorta a 200", r.status_code == 200 and len(r.json()["motivo_rechazo"]) == 200, r.text)
chk("sin motivo usa uno por defecto", client.post("/pagos/rechazo", headers=hc, json={"pedido_id": pid, "metodo": "transferencia"}).json()["motivo_rechazo"])
chk("propina negativa → 422", client.post("/pagos/rechazo", headers=hc, json={"pedido_id": pid, "metodo": "tarjeta", "propina": -5}).status_code == 422)
chk("método inválido → 422", client.post("/pagos/rechazo", headers=hc, json={"pedido_id": pid, "metodo": "bitcoin"}).status_code == 422)
chk("pedido inexistente → 404", client.post("/pagos/rechazo", headers=hc, json={"pedido_id": 9999, "metodo": "tarjeta"}).status_code == 404)
chk("pedido ajeno → 403", client.post("/pagos/rechazo", headers=ho, json={"pedido_id": pid, "metodo": "tarjeta"}).status_code == 403)
chk("sin sesión → 401/403", client.post("/pagos/rechazo", json={"pedido_id": pid, "metodo": "tarjeta"}).status_code in (401, 403))

# ── Pago aprobado con referencia del portal ──
r = client.post("/pagos/", headers=hc, json={"pedido_id": pid, "metodo": "tarjeta", "referencia": "WLP-ZZ99AA11"})
d = r.json()
chk("el pago aprobado guarda la referencia del portal", r.status_code == 200 and d["estado"] == "aprobado" and d["referencia"] == "WLP-ZZ99AA11", r.text)
chk("genera la factura", d["factura"] and d["factura"]["numero"].startswith("F-"), r.text)

pid2 = pedido()
r = client.post("/pagos/", headers=hc, json={"pedido_id": pid2, "metodo": "transferencia"})
chk("sin referencia usa la del servidor (SIM-)", r.status_code == 200 and r.json()["referencia"].startswith("SIM-"), r.text)
pid3 = pedido()
r = client.post("/pagos/", headers=hc, json={"pedido_id": pid3, "metodo": "tarjeta", "referencia": "<script>"})
chk("referencia maliciosa se ignora", r.status_code == 200 and r.json()["referencia"].startswith("SIM-"), r.text)

chk("pedido ya pagado no admite rechazo → 400", client.post("/pagos/rechazo", headers=hc, json={"pedido_id": pid, "metodo": "tarjeta"}).status_code == 400)

# ── Historial ──
r = client.get("/pagos/mis-pagos", headers=hc)
h = r.json()
chk("historial devuelve rechazados y aprobados", r.status_code == 200 and {"aprobado", "rechazado"} <= {p["estado"] for p in h}, r.text)
chk("cantidad correcta (3 rechazos + 3 aprobados)", len(h) == 6, str(len(h)))
chk("ordenado del más reciente al más antiguo", [p["id"] for p in h] == sorted([p["id"] for p in h], reverse=True))
chk("los aprobados traen su factura", all(p["factura"] for p in h if p["estado"] == "aprobado"))
chk("el historial es solo del cliente", client.get("/pagos/mis-pagos", headers=ho).json() == [])
chk("sin sesión no hay historial", client.get("/pagos/mis-pagos").status_code in (401, 403))

print(f"\n{ok} ok, {fail} fallas")
sys.exit(1 if fail else 0)
