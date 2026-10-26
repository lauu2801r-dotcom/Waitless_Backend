from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import restaurante_id_de, solo_admin
from app.modules.reportes import service
from app.modules.reportes.schemas import DashboardRespuesta

router = APIRouter()


@router.get("/dashboard", response_model=DashboardRespuesta)
def dashboard(
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    return service.obtener_dashboard(db, restaurante_id_de(db, current_user))
