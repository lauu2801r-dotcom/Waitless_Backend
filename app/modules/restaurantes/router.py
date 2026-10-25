from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import restaurante_id_de, solo_admin
from app.modules.auditoria import service as auditoria
from app.modules.auth.models import Restaurante
from app.modules.mesas.models import EstadoMesa, Mesa
from app.modules.menu.models import Producto
from app.modules.restaurantes.schemas import RestauranteActualizar, RestauranteRespuesta

router = APIRouter()


def _armar(db: Session, r: Restaurante) -> RestauranteRespuesta:
    productos = (
        db.query(Producto)
        .filter(Producto.restaurante_id == r.id, Producto.activo.is_(True), Producto.disponible.is_(True))
        .all()
    )
    libres = (
        db.query(Mesa)
        .filter(Mesa.restaurante_id == r.id, Mesa.activa.is_(True), Mesa.estado == EstadoMesa.libre)
        .count()
    )
    return RestauranteRespuesta(
        id=r.id, nombre=r.nombre, descripcion=r.descripcion, tipo_cocina=r.tipo_cocina,
        emoji=r.emoji, activo=bool(r.activo), total_platos=len(productos), mesas_libres=libres,
        categorias=sorted({p.categoria for p in productos if p.categoria}),
    )


@router.get("/", response_model=List[RestauranteRespuesta])
def listar_restaurantes(db: Session = Depends(get_db)):
    """Lista pública: los restaurantes entre los que el cliente elige."""
    restaurantes = db.query(Restaurante).filter(Restaurante.activo.is_(True)).order_by(Restaurante.id).all()
    return [_armar(db, r) for r in restaurantes]


@router.get("/{restaurante_id}", response_model=RestauranteRespuesta)
def obtener_restaurante(restaurante_id: int, db: Session = Depends(get_db)):
    r = db.query(Restaurante).filter(Restaurante.id == restaurante_id).first()
    if not r:
        raise HTTPException(404, "Restaurante no encontrado")
    return _armar(db, r)


@router.patch("/mi-restaurante/datos", response_model=RestauranteRespuesta)
def editar_mi_restaurante(
    datos: RestauranteActualizar, request: Request,
    db: Session = Depends(get_db), current_user: dict = Depends(solo_admin),
):
    """El administrador edita los datos de SU restaurante (nombre, descripción, tipo de cocina)."""
    rid = restaurante_id_de(db, current_user)
    r = db.query(Restaurante).filter(Restaurante.id == rid).first() if rid else None
    if not r:
        raise HTTPException(404, "Tu cuenta no tiene un restaurante asociado")
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(r, campo, valor)
    db.commit()
    db.refresh(r)
    auditoria.registrar(
        db, "restaurante_modificado", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="restaurante", entidad_id=r.id,
        ip=auditoria.ip_de(request),
    )
    return _armar(db, r)
