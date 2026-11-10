from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.auditoria import service as auditoria
from app.modules.privacidad import service

router = APIRouter()


class EliminarCuenta(BaseModel):
    password: str
    confirmacion: str  # la palabra ELIMINAR


@router.get("/mis-datos")
def mis_datos(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Derecho de acceso: todo lo que WaitLess guarda de ti (Ley 1581 de 2012)."""
    uid = int(current_user["sub"])
    datos = service.exportar(db, uid)
    auditoria.registrar(db, "datos_personales_consultados", usuario_id=uid,
                        email=current_user["email"], entidad="usuario", entidad_id=uid)
    return datos


@router.post("/eliminar-cuenta")
def eliminar_cuenta(
    datos: EliminarCuenta, request: Request,
    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user),
):
    """
    Derecho de supresión: anonimiza tu cuenta, cancela tus reservas vigentes y borra
    notificaciones, favoritos y comentarios. Pide tu contraseña y la palabra ELIMINAR.
    """
    uid = int(current_user["sub"])
    anonimo = service.eliminar_cuenta(db, uid, datos.password, datos.confirmacion)
    auditoria.registrar(db, "cuenta_eliminada", usuario_id=uid, email=anonimo,
                        entidad="usuario", entidad_id=uid, ip=auditoria.ip_de(request))
    return {"message": "Tu cuenta fue eliminada y tus datos personales anonimizados"}
