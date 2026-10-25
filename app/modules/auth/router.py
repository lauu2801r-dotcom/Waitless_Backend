from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.modules.auth import service
from app.modules.auditoria import service as auditoria
from app.modules.auth.schemas import (
    UsuarioRegistro,
    UsuarioLogin,
    VerificarOTP,
    ReenviarOTP,
    TokenRespuesta
)

router = APIRouter()

def _ip(request: Request):
    return request.client.host if request.client else None


@router.post("/register")
async def registrar(datos: UsuarioRegistro, request: Request, db: Session = Depends(get_db)):
    resultado = await service.registrar_usuario(db, datos)
    auditoria.registrar(
        db, "registro", email=datos.email.lower().strip(),
        detalle=f"rol={datos.rol.value if datos.rol else 'cliente'}", ip=_ip(request),
    )
    return resultado

@router.post("/verify-otp", response_model=TokenRespuesta)
async def verificar(datos: VerificarOTP, request: Request, db: Session = Depends(get_db)):
    resultado = await service.verificar_otp(db, datos)
    auditoria.registrar(
        db, "cuenta_verificada", usuario_id=resultado["usuario"]["id"],
        email=datos.email.lower().strip(), ip=_ip(request),
    )
    return resultado

@router.post("/login", response_model=TokenRespuesta)
async def login(datos: UsuarioLogin, request: Request, db: Session = Depends(get_db)):
    email = datos.email.lower().strip()
    try:
        resultado = await service.login_usuario(db, datos)
    except HTTPException as e:
        auditoria.registrar(
            db, "login_fallido", email=email, detalle=str(e.detail), ip=_ip(request),
        )
        raise
    auditoria.registrar(
        db, "login_exitoso", usuario_id=resultado["usuario"]["id"],
        email=email, ip=_ip(request),
    )
    return resultado

@router.post("/resend-otp")
async def reenviar(datos: ReenviarOTP, db: Session = Depends(get_db)):
    return await service.reenviar_otp(db, datos.email)

@router.get("/politica-privacidad")
def politica_privacidad():
    """Política de tratamiento de datos personales (RNF-005, Ley 1581 de 2012)."""
    return {
        "version": service.POLITICA_VERSION,
        "titulo": "Política de tratamiento de datos personales de WaitLess",
        "texto": (
            "WaitLess recolecta tu nombre, apellido, correo electrónico y teléfono "
            "con el fin de gestionar tu cuenta, tus reservas y pedidos, enviarte "
            "notificaciones del servicio y mejorar las estimaciones de tiempos de espera. "
            "Tus datos no se venden ni se comparten con terceros no autorizados. "
            "De acuerdo con la Ley 1581 de 2012 tienes derecho a conocer, actualizar, "
            "rectificar y solicitar la supresión de tus datos, así como a revocar tu "
            "autorización. Para ejercer estos derechos escribe a: lauu2801r@gmail.com"
        ),
    }