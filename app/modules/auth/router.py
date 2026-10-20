from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.modules.auth import service
from app.modules.auth.schemas import (
    UsuarioRegistro,
    UsuarioLogin,
    VerificarOTP,
    ReenviarOTP,
    TokenRespuesta
)

router = APIRouter()

@router.post("/register")
async def registrar(datos: UsuarioRegistro, db: Session = Depends(get_db)):
    return await service.registrar_usuario(db, datos)

@router.post("/verify-otp", response_model=TokenRespuesta)
async def verificar(datos: VerificarOTP, db: Session = Depends(get_db)):
    return await service.verificar_otp(db, datos)

@router.post("/login", response_model=TokenRespuesta)
async def login(datos: UsuarioLogin, db: Session = Depends(get_db)):
    return await service.login_usuario(db, datos)

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