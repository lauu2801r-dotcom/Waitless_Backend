import hmac
import logging
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    generate_otp,
    get_password_hash,
    verify_password,
)
from app.modules.auth.models import Restaurante, RolUsuario, Usuario
from app.modules.auth.schemas import UsuarioLogin, UsuarioRegistro, VerificarOTP

logger = logging.getLogger("waitless.auth")

# Límites anti fuerza bruta
MAX_INTENTOS_LOGIN = 5      # fallos de contraseña antes de bloquear
BLOQUEO_MINUTOS = 15        # duración del bloqueo
MAX_INTENTOS_OTP = 5        # códigos OTP incorrectos antes de invalidarlo

# Versión vigente de la política de tratamiento de datos (Ley 1581 de 2012)
POLITICA_VERSION = "1.0"

MSG_OTP_INVALIDO = "Código inválido o expirado. Solicita uno nuevo"
MSG_OTP_REENVIADO = "Si la cuenta existe y está pendiente de verificación, te enviamos un código"

conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
)


async def enviar_otp_email(email: str, otp: str):
    message = MessageSchema(
        subject="WaitLess - Código de verificación",
        recipients=[email],
        body=f"""
        <h2>Verificación de cuenta WaitLess</h2>
        <p>Tu código de verificación es:</p>
        <h1 style="color: #E8643C; letter-spacing: 8px;">{otp}</h1>
        <p>Este código expira en 10 minutos.</p>
        <p>Si no solicitaste este código, ignora este mensaje.</p>
        """,
        subtype="html",
    )
    fm = FastMail(conf)
    await fm.send_message(message)


def _construir_respuesta_usuario(usuario: Usuario, db: Session) -> dict:
    """Construye el dict del usuario incluyendo nombre_restaurante si es admin."""
    nombre_restaurante = None
    if usuario.rol == RolUsuario.administrador:
        restaurante = (
            db.query(Restaurante)
            .filter(Restaurante.administrador_id == usuario.id)
            .first()
        )
        if restaurante:
            nombre_restaurante = restaurante.nombre

    return {
        "id": usuario.id,
        "nombre": usuario.nombre,
        "apellido": usuario.apellido,
        "email": usuario.email,
        "telefono": usuario.telefono,
        "rol": usuario.rol,
        "verificado": usuario.verificado,
        "creado_en": usuario.creado_en,
        "nombre_restaurante": nombre_restaurante,
    }


def _codigo_negocio_valido(codigo: str | None) -> bool:
    """Compara el código recibido con el configurado en el servidor (.env)."""
    esperado = settings.CODIGO_NEGOCIO
    if not esperado:
        logger.error("CODIGO_NEGOCIO no está configurado en el .env")
        return False
    if not codigo:
        return False
    return hmac.compare_digest(codigo.strip().encode(), esperado.encode())


async def _enviar_otp_seguro(email: str, otp: str):
    """Envía el OTP sin tumbar la petición si el correo falla."""
    try:
        await enviar_otp_email(email, otp)
    except Exception as e:
        logger.warning("No se pudo enviar el correo a %s: %s", email, e)


async def registrar_usuario(db: Session, datos: UsuarioRegistro):
    email_normalizado = datos.email.lower().strip()

    # Solo se puede auto-registrar un cliente o un administrador.
    # Las cuentas de empleado las crea un administrador (HU de roles).
    if datos.rol == RolUsuario.empleado:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Las cuentas de empleado las crea un administrador",
        )

    # Consentimiento obligatorio (Ley 1581 de 2012, R-008)
    if not datos.acepta_politica:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debes aceptar la política de tratamiento de datos personales para registrarte",
        )

    if datos.rol == RolUsuario.administrador:
        if not datos.nombre_restaurante or not datos.codigo_negocio:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El nombre del restaurante y el código de negocio son obligatorios para administradores",
            )
        if not _codigo_negocio_valido(datos.codigo_negocio):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Código de negocio inválido. Verifica con tu proveedor.",
            )

    try:
        ahora = datetime.utcnow()
        usuario_existente = (
            db.query(Usuario).filter(Usuario.email == email_normalizado).first()
        )

        if usuario_existente:
            if usuario_existente.verificado:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El correo ya está registrado",
                )
            otp = generate_otp()
            usuario_existente.otp_code = otp
            usuario_existente.otp_expira = ahora + timedelta(minutes=10)
            usuario_existente.otp_intentos = 0
            usuario_existente.politica_version = POLITICA_VERSION
            usuario_existente.politica_aceptada_en = ahora
            db.commit()
            await _enviar_otp_seguro(email_normalizado, otp)
            return {"message": "Código reenviado a tu correo"}

        otp = generate_otp()
        nuevo_usuario = Usuario(
            nombre=datos.nombre,
            apellido=datos.apellido,
            email=email_normalizado,
            telefono=datos.telefono,
            rol=datos.rol,
            hashed_password=get_password_hash(datos.password),
            otp_code=otp,
            otp_expira=ahora + timedelta(minutes=10),
            politica_version=POLITICA_VERSION,
            politica_aceptada_en=ahora,
        )
        db.add(nuevo_usuario)
        db.flush()

        if datos.rol == RolUsuario.administrador:
            db.add(
                Restaurante(
                    nombre=datos.nombre_restaurante,
                    codigo_negocio=datos.codigo_negocio.strip(),
                    administrador_id=nuevo_usuario.id,
                )
            )

        db.commit()
        db.refresh(nuevo_usuario)
        logger.info("Usuario registrado id=%s rol=%s", nuevo_usuario.id, nuevo_usuario.rol)

        await _enviar_otp_seguro(email_normalizado, otp)

        return {"message": "Usuario registrado. Revisa tu correo para verificar tu cuenta"}

    except HTTPException:
        raise
    except Exception:
        db.rollback()
        logger.exception("Error en el registro de usuario")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al registrar. Intenta de nuevo",
        )


async def verificar_otp(db: Session, datos: VerificarOTP):
    email_normalizado = datos.email.lower().strip()

    usuario = db.query(Usuario).filter(Usuario.email == email_normalizado).first()

    # Mensaje genérico: no revela si el correo existe o si ya está verificado
    if not usuario or usuario.verificado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=MSG_OTP_INVALIDO,
        )

    # ¿Hay un código vigente?
    if (
        not usuario.otp_code
        or usuario.otp_expira is None
        or datetime.utcnow() > usuario.otp_expira
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=MSG_OTP_INVALIDO,
        )

    # ¿Es el código correcto? (si no, cuenta el intento)
    if not hmac.compare_digest(
        usuario.otp_code.encode(), datos.otp.strip().encode()
    ):
        usuario.otp_intentos = (usuario.otp_intentos or 0) + 1
        if usuario.otp_intentos >= MAX_INTENTOS_OTP:
            usuario.otp_code = None
            usuario.otp_expira = None
            usuario.otp_intentos = 0
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Demasiados intentos. Solicita un código nuevo",
            )
        restantes = MAX_INTENTOS_OTP - usuario.otp_intentos
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Código incorrecto. Te quedan {restantes} intentos",
        )

    usuario.verificado = True
    usuario.otp_code = None
    usuario.otp_expira = None
    usuario.otp_intentos = 0
    db.commit()
    db.refresh(usuario)

    token = create_access_token(
        data={"sub": str(usuario.id), "email": usuario.email, "rol": usuario.rol}
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "usuario": _construir_respuesta_usuario(usuario, db),
    }


async def login_usuario(db: Session, datos: UsuarioLogin):
    email_normalizado = datos.email.lower().strip()

    usuario = db.query(Usuario).filter(Usuario.email == email_normalizado).first()

    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
        )

    # ¿Cuenta bloqueada temporalmente?
    ahora = datetime.utcnow()
    if usuario.bloqueado_hasta and ahora < usuario.bloqueado_hasta:
        minutos = int((usuario.bloqueado_hasta - ahora).total_seconds() // 60) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos fallidos. Intenta de nuevo en {minutos} minutos",
        )

    if not verify_password(datos.password, usuario.hashed_password):
        usuario.login_intentos = (usuario.login_intentos or 0) + 1
        if usuario.login_intentos >= MAX_INTENTOS_LOGIN:
            usuario.bloqueado_hasta = ahora + timedelta(minutes=BLOQUEO_MINUTOS)
            usuario.login_intentos = 0
            db.commit()
            logger.warning("Cuenta bloqueada por intentos fallidos id=%s", usuario.id)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Demasiados intentos fallidos. Cuenta bloqueada {BLOQUEO_MINUTOS} minutos",
            )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
        )

    # Contraseña correcta: se reinician los contadores
    usuario.login_intentos = 0
    usuario.bloqueado_hasta = None
    db.commit()

    if not usuario.verificado:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta no verificada. Revisa tu correo",
        )

    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta desactivada",
        )

    token = create_access_token(
        data={"sub": str(usuario.id), "email": usuario.email, "rol": usuario.rol}
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "usuario": _construir_respuesta_usuario(usuario, db),
    }


async def reenviar_otp(db: Session, email: str):
    email_normalizado = email.lower().strip()

    usuario = db.query(Usuario).filter(Usuario.email == email_normalizado).first()

    # Misma respuesta exista o no la cuenta: no se filtra qué correos están registrados
    if not usuario or usuario.verificado:
        return {"message": MSG_OTP_REENVIADO}

    otp = generate_otp()
    usuario.otp_code = otp
    usuario.otp_expira = datetime.utcnow() + timedelta(minutes=10)
    usuario.otp_intentos = 0
    db.commit()

    await _enviar_otp_seguro(email_normalizado, otp)

    return {"message": MSG_OTP_REENVIADO}