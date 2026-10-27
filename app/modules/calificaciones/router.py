from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import restaurante_id_de, solo_admin, get_current_user
from app.modules.calificaciones import service
from app.modules.calificaciones.schemas import (
    CalificacionCrear, EstadoCalificacionPedido, ResumenCalificaciones,
)

router = APIRouter()


@router.post("/", response_model=EstadoCalificacionPedido)
def calificar_pedido(
    datos: CalificacionCrear,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """El cliente califica (1 a 5 estrellas) los platos de un pedido ya pagado. Solo una vez por pedido."""
    return service.calificar(db, datos, int(current_user["sub"]))


@router.get("/pedido/{pedido_id}", response_model=EstadoCalificacionPedido)
def calificacion_del_pedido(
    pedido_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """¿Ya está pagado? ¿Ya lo calificaste? Sirve para mostrar el botón «Calificar»."""
    return service.estado_del_pedido(db, pedido_id, int(current_user["sub"]))


@router.get("/resumen", response_model=ResumenCalificaciones)
def resumen_calificaciones(
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    """Promedio, distribución, mejores platos y comentarios recientes de TU restaurante."""
    return service.resumen(db, restaurante_id_de(db, current_user))
