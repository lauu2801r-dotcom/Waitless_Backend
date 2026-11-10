"""
Pruebas de "Olvidé mi contraseña" (RF: recuperación de cuenta).
Se ejecuta con una base SQLite temporal y sin enviar correos reales.
    python -m pytest test_recuperar_password.py -q      (o)      python test_recuperar_password.py
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
from app.core.security import get_password_hash
from app.modules.auth import service
from app.modules.auth.models import Usuario, RolUsuario

ENVIADOS = []
async def _falso(email, otp):          # no se envía correo de verdad
    ENVIADOS.append((email, otp))
service.enviar_recuperacion_email = _falso

db = SessionLocal()
def mk(email, verificado=True, activo=True):
    u = Usuario(nombre="Ana", apellido="Paz", email=email, rol=RolUsuario.cliente,
                hashed_password=get_password_hash("Vieja1234"), verificado=verificado, activo=activo)
    db.add(u); db.commit(); return u.id
mk("ok@x.co"); mk("sinverificar@x.co", verificado=False); mk("inactiva@x.co", activo=False)

def u(email):
    db.expire_all(); return db.query(Usuario).filter(Usuario.email == email).first()

def retroceder_envio(email, segundos=120):
    """Simula que el código se envió hace `segundos` (para saltar la espera anti-spam)."""
    x = u(email); x.otp_expira = x.otp_expira - timedelta(seconds=segundos); db.commit()

ok = fail = 0
def check(n, c):
    global ok, fail
    print(("PASS " if c else "FAIL ") + n); ok += bool(c); fail += (not c)

def test_todo():
    with TestClient(app) as c:
        # 1. respuesta idéntica exista o no la cuenta
        r1 = c.post("/auth/forgot-password", json={"email": "ok@x.co"})
        r2 = c.post("/auth/forgot-password", json={"email": "nadie@x.co"})
        check("solicitud responde 200", r1.status_code == 200 and r2.status_code == 200)
        check("misma respuesta exista o no la cuenta", r1.json() == r2.json())
        check("se envió correo solo a la cuenta real", [e for e, _ in ENVIADOS] == ["ok@x.co"])
        # 2. cuentas sin verificar / inactivas no reciben código
        c.post("/auth/forgot-password", json={"email": "sinverificar@x.co"})
        c.post("/auth/forgot-password", json={"email": "inactiva@x.co"})
        check("sin verificar o inactiva: no se envía", len(ENVIADOS) == 1)
        # 3. anti-spam
        c.post("/auth/forgot-password", json={"email": "ok@x.co"})
        check("anti-spam: no reenvía antes de 60 s", len(ENVIADOS) == 1)
        codigo = ENVIADOS[0][1]
        check("código de 6 dígitos", len(codigo) == 6 and codigo.isdigit())
        # 4. validaciones de la nueva contraseña
        body = lambda **k: {"email": "ok@x.co", "otp": codigo, "nueva_password": "Nueva1234", **k}
        check("rechaza contraseña corta", c.post("/auth/reset-password", json=body(nueva_password="Ab1")).status_code == 422)
        check("rechaza sin mayúscula", c.post("/auth/reset-password", json=body(nueva_password="nueva12345")).status_code == 422)
        check("rechaza sin número", c.post("/auth/reset-password", json=body(nueva_password="NuevaClave")).status_code == 422)
        # 5. código incorrecto cuenta intentos y se invalida a los 5
        r = c.post("/auth/reset-password", json=body(otp="000000" if codigo != "000000" else "111111"))
        check("código incorrecto -> 400 con intentos restantes", r.status_code == 400 and "4 intentos" in r.json()["detail"])
        for _ in range(4):
            r = c.post("/auth/reset-password", json=body(otp="999999" if codigo != "999999" else "888888"))
        check("a los 5 fallos se invalida el código", r.status_code == 400 and "Demasiados" in r.json()["detail"])
        check("con el código invalidado ni el correcto sirve", c.post("/auth/reset-password", json=body()).status_code == 400)
        check("la contraseña vieja sigue funcionando", c.post("/auth/login", json={"email": "ok@x.co", "password": "Vieja1234"}).status_code == 200)
        # 6. flujo feliz
        c.post("/auth/forgot-password", json={"email": "ok@x.co"})
        codigo2 = ENVIADOS[-1][1]
        check("segundo código enviado", len(ENVIADOS) == 2)
        r = c.post("/auth/reset-password", json={"email": "ok@x.co", "otp": codigo2, "nueva_password": "Nueva1234"})
        check("restablece la contraseña", r.status_code == 200)
        check("login con la nueva funciona", c.post("/auth/login", json={"email": "ok@x.co", "password": "Nueva1234"}).status_code == 200)
        check("login con la vieja ya no funciona", c.post("/auth/login", json={"email": "ok@x.co", "password": "Vieja1234"}).status_code == 401)
        check("el código es de un solo uso", c.post("/auth/reset-password", json={"email": "ok@x.co", "otp": codigo2, "nueva_password": "Otra12345"}).status_code == 400)
        # 7. código vencido
        c.post("/auth/forgot-password", json={"email": "ok@x.co"}); cod3 = ENVIADOS[-1][1]
        x = u("ok@x.co"); x.otp_expira = datetime.utcnow() - timedelta(seconds=1); db.commit()
        check("código vencido se rechaza", c.post("/auth/reset-password", json={"email": "ok@x.co", "otp": cod3, "nueva_password": "Otra12345"}).status_code == 400)
        # 8. desbloquea cuenta bloqueada
        x = u("ok@x.co"); x.bloqueado_hasta = datetime.utcnow() + timedelta(minutes=15); x.otp_code = None; x.otp_expira = None; db.commit()
        c.post("/auth/forgot-password", json={"email": "ok@x.co"}); cod4 = ENVIADOS[-1][1]
        r = c.post("/auth/reset-password", json={"email": "ok@x.co", "otp": cod4, "nueva_password": "Desbloq123"})
        check("restablecer desbloquea la cuenta", r.status_code == 200 and c.post("/auth/login", json={"email": "ok@x.co", "password": "Desbloq123"}).status_code == 200)
        # 9. correos inexistentes / sin verificar no pueden restablecer
        check("correo inexistente -> 400 genérico", c.post("/auth/reset-password", json={"email": "nadie@x.co", "otp": "123456", "nueva_password": "Nueva1234"}).status_code == 400)
        check("cuenta sin verificar -> 400", c.post("/auth/reset-password", json={"email": "sinverificar@x.co", "otp": "123456", "nueva_password": "Nueva1234"}).status_code == 400)
    assert fail == 0, f"{fail} pruebas fallaron"

if __name__ == "__main__":
    test_todo()
    print(f"\n{ok} OK, {fail} fallos")
