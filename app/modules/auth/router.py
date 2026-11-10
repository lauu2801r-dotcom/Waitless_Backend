from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import get_password_hash, verify_password
from app.modules.auth.models import Usuario
from app.modules.auth import service
from app.modules.auditoria import service as auditoria
from app.modules.auth.schemas import (
    UsuarioRegistro,
    UsuarioLogin,
    VerificarOTP,
    ReenviarOTP,
    OlvidePassword,
    RestablecerPassword,
    CambiarPassword,
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

@router.post("/forgot-password")
async def olvide_password(datos: OlvidePassword, request: Request, db: Session = Depends(get_db)):
    """Envía un código al correo para recuperar la contraseña (respuesta siempre igual)."""
    resultado = await service.solicitar_recuperacion(db, datos.email)
    auditoria.registrar(
        db, "recuperacion_solicitada", email=datos.email.lower().strip(), ip=_ip(request),
    )
    return resultado

@router.post("/reset-password")
async def restablecer(datos: RestablecerPassword, request: Request, db: Session = Depends(get_db)):
    """Cambia la contraseña usando el código recibido por correo."""
    email = datos.email.lower().strip()
    try:
        resultado = await service.restablecer_password(db, datos)
    except HTTPException as e:
        auditoria.registrar(
            db, "recuperacion_fallida", email=email, detalle=str(e.detail), ip=_ip(request),
        )
        raise
    auditoria.registrar(db, "password_restablecida", email=email, ip=_ip(request))
    return resultado

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


@router.post("/change-password")
def cambiar_password(
    datos: CambiarPassword, request: Request,
    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user),
):
    """Cambia la contraseña de la sesión actual pidiendo la contraseña vigente."""
    usuario = db.query(Usuario).filter(Usuario.id == int(current_user["sub"])).first()
    if not usuario or not verify_password(datos.password_actual, usuario.hashed_password):
        auditoria.registrar(db, "cambio_password_fallido", usuario_id=int(current_user["sub"]),
                            email=current_user["email"], ip=_ip(request))
        raise HTTPException(status_code=400, detail="La contraseña actual no es correcta")
    if verify_password(datos.nueva_password, usuario.hashed_password):
        raise HTTPException(status_code=400, detail="La nueva contraseña debe ser diferente a la actual")
    usuario.hashed_password = get_password_hash(datos.nueva_password)
    db.commit()
    auditoria.registrar(db, "cambio_password", usuario_id=usuario.id, email=usuario.email, ip=_ip(request))
    return {"message": "Contraseña actualizada"}
