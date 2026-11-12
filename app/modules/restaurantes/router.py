import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import restaurante_id_de, solo_admin
from app.modules.auditoria import service as auditoria
from app.modules.auth.models import Restaurante
from app.modules.mesas.models import EstadoMesa, Mesa
from app.modules.menu.models import Producto
from app.modules.calificaciones.service import promedio_restaurante
from app.modules.restaurantes import horarios as horarios_mod
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
    prom, n_cal = promedio_restaurante(db, r.id)
    try:
        galeria = [u for u in json.loads(r.galeria or "[]") if isinstance(u, str)]
    except (ValueError, TypeError):
        galeria = []
    abierto, _ = horarios_mod.estado_en(r.horarios, horarios_mod.ahora_colombia())
    return RestauranteRespuesta(
        direccion=r.direccion, telefono=r.telefono, instagram=r.instagram,
        horarios=horarios_mod.leer(r.horarios), galeria=galeria, abierto_ahora=abierto,
        minutos_alerta_mesa=r.minutos_alerta_mesa or 90,
        domicilio_activo=True if r.domicilio_activo is None else bool(r.domicilio_activo),
        costo_domicilio=5000 if r.costo_domicilio is None else r.costo_domicilio,
        pedido_minimo_domicilio=r.pedido_minimo_domicilio or 0,
        calificacion_promedio=prom, total_calificaciones=n_cal,
        id=r.id, nombre=r.nombre, descripcion=r.descripcion, tipo_cocina=r.tipo_cocina,
        emoji=r.emoji, imagen_url=r.imagen_url, activo=bool(r.activo), total_platos=len(productos), mesas_libres=libres,
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


@router.get("/mi-restaurante/datos", response_model=RestauranteRespuesta)
def ver_mi_restaurante(db: Session = Depends(get_db), current_user: dict = Depends(solo_admin)):
    """Datos completos de TU restaurante (contacto, horarios, galería)."""
    rid = restaurante_id_de(db, current_user)
    r = db.query(Restaurante).filter(Restaurante.id == rid).first() if rid else None
    if not r:
        raise HTTPException(404, "Tu cuenta no tiene un restaurante asociado")
    return _armar(db, r)


@router.patch("/mi-restaurante/datos", response_model=RestauranteRespuesta)
def editar_mi_restaurante(
    datos: RestauranteActualizar, request: Request,
    db: Session = Depends(get_db), current_user: dict = Depends(solo_admin),
):
    """El administrador edita los datos de SU restaurante: nombre, descripción, contacto, horarios (con días especiales) y galería."""
    rid = restaurante_id_de(db, current_user)
    r = db.query(Restaurante).filter(Restaurante.id == rid).first() if rid else None
    if not r:
        raise HTTPException(404, "Tu cuenta no tiene un restaurante asociado")
    cambios = datos.model_dump(exclude_unset=True)
    for k in ("nombre", "minutos_alerta_mesa", "domicilio_activo", "costo_domicilio", "pedido_minimo_domicilio"):
        if k in cambios and cambios[k] is None:
            cambios.pop(k)
    if "horarios" in cambios:
        cambios["horarios"] = horarios_mod.serializar(datos.horarios) if datos.horarios else None
    if "galeria" in cambios:
        cambios["galeria"] = json.dumps(cambios["galeria"] or [], ensure_ascii=False)
    for campo, valor in cambios.items():
        if isinstance(valor, str) and campo in ("direccion", "telefono", "instagram"):
            valor = valor.strip() or None
        setattr(r, campo, valor)
    db.commit()
    db.refresh(r)
    auditoria.registrar(
        db, "restaurante_modificado", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="restaurante", entidad_id=r.id,
        ip=auditoria.ip_de(request),
    )
    return _armar(db, r)
