from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.clientes import service
from app.modules.clientes.schemas import FavoritoRespuesta, ResumenCliente

router = APIRouter()


@router.get("/resumen", response_model=ResumenCliente)
def mi_resumen(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Datos reales del perfil: visitas, nivel, facturas, favoritos y gasto."""
    return service.resumen(db, int(current_user["sub"]))


@router.get("/favoritos", response_model=List[FavoritoRespuesta])
def mis_favoritos(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return service.listar_favoritos(db, int(current_user["sub"]))


@router.put("/favoritos/{producto_id}", status_code=204)
def marcar_favorito(
    producto_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user),
):
    service.agregar_favorito(db, int(current_user["sub"]), producto_id)


@router.delete("/favoritos/{producto_id}", status_code=204)
def quitar_favorito(
    producto_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user),
):
    service.quitar_favorito(db, int(current_user["sub"]), producto_id)
