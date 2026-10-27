from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.notificaciones import service
from app.modules.notificaciones.schemas import ContadorNotificaciones, NotificacionRespuesta

router = APIRouter()


@router.get("/", response_model=List[NotificacionRespuesta])
def mis_notificaciones(
    solo_no_leidas: bool = False,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Notificaciones del usuario (las más recientes primero)."""
    return service.listar(db, int(current_user["sub"]), solo_no_leidas)


@router.get("/contador", response_model=ContadorNotificaciones)
def contador(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return {"no_leidas": service.contar_no_leidas(db, int(current_user["sub"]))}


@router.post("/leer-todas", response_model=ContadorNotificaciones)
def leer_todas(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    service.marcar_todas_leidas(db, int(current_user["sub"]))
    return {"no_leidas": 0}


@router.patch("/{notificacion_id}/leer", response_model=NotificacionRespuesta)
def leer(
    notificacion_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return service.marcar_leida(db, notificacion_id, int(current_user["sub"]))


@router.delete("/{notificacion_id}")
def borrar(
    notificacion_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service.eliminar(db, notificacion_id, int(current_user["sub"]))
    return {"message": "Notificación eliminada"}
