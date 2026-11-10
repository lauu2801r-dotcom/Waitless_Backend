"""
Pruebas del módulo Negocio: contacto, horarios (con días especiales), galería,
reservas según horario y cambio de contraseña.
    python tests/test_negocio.py        (desde la carpeta del backend)
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
from app.modules.mesas.models import Mesa
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
mesa = Mesa(numero=1, restaurante_id=ra.id, capacidad=4); mesa2 = Mesa(numero=2, restaurante_id=ra.id, capacidad=4)
db.add_all([mesa, mesa2]); db.commit()
client = TestClient(app)
ok = fail = 0
def chk(n, c, extra=""):
    global ok, fail
    if c: ok += 1; print("  ok  ", n)
    else: fail += 1; print("  FALLA", n, extra)

def proximo(dia_sem, hora, minuto=0, semanas=1):
    """Próxima fecha futura en ese día de la semana (0=lunes) a esa hora, como ISO local."""
    base = datetime.utcnow() - timedelta(hours=5)
    d = base + timedelta(days=(dia_sem - base.weekday()) % 7 + 7 * (semanas - 1) + (7 if (dia_sem - base.weekday()) % 7 == 0 else 0))
    return d.replace(hour=hora, minute=minuto, second=0, microsecond=0)

# ── Contacto ──
r = client.patch("/restaurantes/mi-restaurante/datos", headers=ha,
                 json={"direccion": " Cra 7 # 45-10, Bogotá ", "telefono": "+57 601 234 5678", "instagram": "@casasolera"})
chk("admin guarda contacto", r.status_code == 200 and r.json()["direccion"] == "Cra 7 # 45-10, Bogotá"
    and r.json()["telefono"] == "+57 601 234 5678", r.text)
chk("teléfono inválido → 422", client.patch("/restaurantes/mi-restaurante/datos", headers=ha, json={"telefono": "abc"}).status_code == 422)
chk("cliente no puede editar → 403", client.patch("/restaurantes/mi-restaurante/datos", headers=hc, json={"direccion": "x"}).status_code == 403)
r = client.get(f"/restaurantes/{ra.id}")
chk("el contacto es público", r.json()["direccion"] and r.json()["abierto_ahora"] is None, r.text)

r = client.get("/restaurantes/mi-restaurante/datos", headers=ha)
chk("el admin lee los datos de su restaurante", r.status_code == 200 and r.json()["nombre"] == "Casa Solera", r.text)
chk("el cliente no accede → 403", client.get("/restaurantes/mi-restaurante/datos", headers=hc).status_code == 403)

# ── Galería ──
r = client.patch("/restaurantes/mi-restaurante/datos", headers=ha, json={"galeria": ["https://x.co/a.jpg", " ", "https://x.co/b.jpg"]})
chk("galería guarda y limpia vacíos", r.status_code == 200 and r.json()["galeria"] == ["https://x.co/a.jpg", "https://x.co/b.jpg"], r.text)
chk("enlace no http → 422", client.patch("/restaurantes/mi-restaurante/datos", headers=ha, json={"galeria": ["javascript:alert(1)"]}).status_code == 422)
chk("más de 12 imágenes → 422", client.patch("/restaurantes/mi-restaurante/datos", headers=ha, json={"galeria": [f"https://x.co/{i}.jpg" for i in range(13)]}).status_code == 422)

# ── Horarios ──
semana = {d: {"abre": "12:00", "cierra": "22:00"} for d in H.DIAS}; semana["lun"] = None
r = client.patch("/restaurantes/mi-restaurante/datos", headers=ha, json={"horarios": {"semana": semana}})
chk("guarda horarios semanales", r.status_code == 200 and r.json()["horarios"]["semana"]["mar"]["abre"] == "12:00", r.text)
chk("hora inválida → 422", client.patch("/restaurantes/mi-restaurante/datos", headers=ha,
    json={"horarios": {"semana": {"mar": {"abre": "25:00", "cierra": "22:00"}}}}).status_code == 422)
chk("cierre antes de apertura → 422", client.patch("/restaurantes/mi-restaurante/datos", headers=ha,
    json={"horarios": {"semana": {"mar": {"abre": "22:00", "cierra": "12:00"}}}}).status_code == 422)
chk("día inventado → 422", client.patch("/restaurantes/mi-restaurante/datos", headers=ha,
    json={"horarios": {"semana": {"xyz": {"abre": "10:00", "cierra": "12:00"}}}}).status_code == 422)

mar_ok = proximo(1, 19).isoformat(); mar_tarde = proximo(1, 23).isoformat(); lun = proximo(0, 19).isoformat()
def reservar(fecha, mesa_id, h=hc):
    return client.post("/reservas/", headers=h, json={"mesa_id": mesa_id, "fecha_hora": fecha, "numero_personas": 2})
r = reservar(lun, mesa.id)
chk("reservar un día cerrado → 400", r.status_code == 400 and "cerrado" in r.json()["detail"], r.text)
r = reservar(mar_tarde, mesa.id)
chk("reservar fuera de horario → 400", r.status_code == 400 and "12:00 a 22:00" in r.json()["detail"], r.text)
r = reservar(mar_ok, mesa.id)
chk("reservar dentro del horario → 200", r.status_code == 200, r.text)
rid = r.json()["id"]
r = client.patch(f"/reservas/{rid}", headers=hc, json={"fecha_hora": lun})
chk("modificar a un día cerrado → 400", r.status_code == 400, r.text)

# ── Días especiales ──
fecha_mar = proximo(1, 19).date().isoformat()
esp = [{"fecha": fecha_mar, "cerrado": True, "nota": "Evento privado"}]
r = client.patch("/restaurantes/mi-restaurante/datos", headers=ha, json={"horarios": {"semana": semana, "especiales": esp}})
chk("guarda día especial cerrado", r.status_code == 200 and r.json()["horarios"]["especiales"][0]["nota"] == "Evento privado", r.text)
r = reservar(mar_ok, mesa2.id)
chk("el día especial cerrado bloquea aunque el martes normal abra", r.status_code == 400 and "Evento privado" in r.json()["detail"], r.text)
esp = [{"fecha": proximo(0, 19).date().isoformat(), "cerrado": False, "abre": "18:00", "cierra": "21:00", "nota": "Apertura especial"}]
client.patch("/restaurantes/mi-restaurante/datos", headers=ha, json={"horarios": {"semana": semana, "especiales": esp}})
chk("un lunes especial abierto sí permite reservar", reservar(lun, mesa2.id).status_code == 200)
chk("día especial abierto sin horas → 422", client.patch("/restaurantes/mi-restaurante/datos", headers=ha,
    json={"horarios": {"semana": semana, "especiales": [{"fecha": fecha_mar, "cerrado": False}]}}).status_code == 422)

# ── estado_en / abierto_ahora ──
sem = H.Horarios(semana=semana).model_dump(mode="json")
import json as _j
txt = _j.dumps(sem)
chk("estado_en: abierto", H.estado_en(txt, proximo(1, 12))[0] is True)
chk("estado_en: justo a la hora de cierre ya está cerrado", H.estado_en(txt, proximo(1, 22))[0] is False)
chk("estado_en: sin horarios no restringe", H.estado_en(None, proximo(1, 3)) == (None, ""))
r = client.patch("/restaurantes/mi-restaurante/datos", headers=ha, json={"horarios": None})
chk("se pueden quitar los horarios", r.status_code == 200 and r.json()["horarios"] is None and r.json()["abierto_ahora"] is None, r.text)

# ── Cambio de contraseña ──
c = lambda a, n, h=hc: client.post("/auth/change-password", headers=h, json={"password_actual": a, "nueva_password": n})
chk("contraseña actual incorrecta → 400", c("Mala1234", "Nueva1234").status_code == 400)
chk("nueva igual a la actual → 400", c("Abcdefg1", "Abcdefg1").status_code == 400)
chk("nueva débil → 422", c("Abcdefg1", "abc").status_code == 422)
chk("sin sesión → 401/403", client.post("/auth/change-password", json={"password_actual": "a", "nueva_password": "Nueva1234"}).status_code in (401, 403))
r = c("Abcdefg1", "Nueva1234")
chk("cambia la contraseña", r.status_code == 200, r.text)
r = client.post("/auth/login", json={"email": "c@x.co", "password": "Nueva1234"})
chk("puede entrar con la nueva", r.status_code == 200, r.text)
r = client.post("/auth/login", json={"email": "c@x.co", "password": "Abcdefg1"})
chk("la anterior ya no sirve", r.status_code in (400, 401), r.text)

print(f"\n{ok} ok, {fail} fallas")
sys.exit(1 if fail else 0)
