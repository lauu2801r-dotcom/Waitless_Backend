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