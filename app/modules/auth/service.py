from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from datetime import datetime, timedelta
from app.modules.auth.models import Usuario, RolUsuario
from app.modules.auth.schemas import UsuarioRegistro, UsuarioLogin, VerificarOTP
from app.core.security import (
    get_password_hash, 
    verify_password, 
    create_access_token,
    generate_otp
)
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from app.core.config import settings

# Configuración del correo
conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True
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
        subtype="html"
    )
    fm = FastMail(conf)
    await fm.send_message(message)

async def registrar_usuario(db: Session, datos: UsuarioRegistro):
    try:
        email_normalizado = datos.email.lower().strip()
        
        usuario_existente = db.query(Usuario).filter(
            Usuario.email == email_normalizado
        ).first()
        
        if usuario_existente:
            if usuario_existente.verificado:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El correo ya está registrado"
                )
            else:
                otp = generate_otp()
                usuario_existente.otp_code = otp
                usuario_existente.otp_expira = datetime.utcnow() + timedelta(minutes=10)
                db.commit()
                try:
                    await enviar_otp_email(email_normalizado, otp)
                except Exception as e:
                    print(f"Error enviando correo: {e}")
                return {"message": "Código reenviado a tu correo"}

        otp = generate_otp()
        nuevo_usuario = Usuario(
            nombre=datos.nombre,
            apellido=datos.apellido,
            email=email_normalizado,
            telefono=datos.telefono,
            hashed_password=get_password_hash(datos.password),
            otp_code=otp,
            otp_expira=datetime.utcnow() + timedelta(minutes=10)
        )
        db.add(nuevo_usuario)
        db.commit()
        db.refresh(nuevo_usuario)
        print(f"✅ Usuario guardado: {nuevo_usuario.id} - {nuevo_usuario.email}")
        
        try:
            await enviar_otp_email(email_normalizado, otp)
            print(f"✅ Correo enviado a {email_normalizado}")
        except Exception as e:
            print(f"⚠️ Error enviando correo: {e} - pero usuario guardado")
        
        return {"message": "Usuario registrado. Revisa tu correo para verificar tu cuenta"}
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"❌ Error en registro: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al registrar: {str(e)}"
        )

async def verificar_otp(db: Session, datos: VerificarOTP):
    email_normalizado = datos.email.lower().strip()
    print(f"🔍 Buscando usuario con email: {email_normalizado}")
    
    usuario = db.query(Usuario).filter(
        Usuario.email == email_normalizado
    ).first()
    
    print(f"🔍 Usuario encontrado: {usuario}")
    
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    if usuario.verificado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La cuenta ya está verificada"
        )
    
    if usuario.otp_code != datos.otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código incorrecto"
        )
    
    if datetime.utcnow() > usuario.otp_expira:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El código ha expirado. Solicita uno nuevo"
        )
    
    usuario.verificado = True
    usuario.otp_code = None
    usuario.otp_expira = None
    db.commit()
    db.refresh(usuario)
    
    token = create_access_token(data={
        "sub": str(usuario.id),
        "email": usuario.email,
        "rol": usuario.rol
    })
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "usuario": usuario
    }

async def login_usuario(db: Session, datos: UsuarioLogin):
    email_normalizado = datos.email.lower().strip()
    
    usuario = db.query(Usuario).filter(
        Usuario.email == email_normalizado
    ).first()
    
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas"
        )
    
    if not verify_password(datos.password, usuario.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas"
        )
    
    if not usuario.verificado:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta no verificada. Revisa tu correo"
        )
    
    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta desactivada"
        )
    
    token = create_access_token(data={
        "sub": str(usuario.id),
        "email": usuario.email,
        "rol": usuario.rol
    })
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "usuario": usuario
    }

async def reenviar_otp(db: Session, email: str):
    email_normalizado = email.lower().strip()
    
    usuario = db.query(Usuario).filter(
        Usuario.email == email_normalizado
    ).first()
    
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    if usuario.verificado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La cuenta ya está verificada"
        )
    
    otp = generate_otp()
    usuario.otp_code = otp
    usuario.otp_expira = datetime.utcnow() + timedelta(minutes=10)
    db.commit()
    
    try:
        await enviar_otp_email(email_normalizado, otp)
    except Exception as e:
        print(f"Error enviando correo: {e}")
    
    return {"message": "Código reenviado a tu correo"}