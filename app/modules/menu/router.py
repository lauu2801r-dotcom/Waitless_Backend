from typing import List

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import admin_o_empleado, restaurante_id_de, solo_admin
from app.modules.auditoria import service as auditoria
from app.modules.menu import service
from app.modules.calificaciones.service import adjuntar_a_productos
from app.modules.menu.schemas import (
    ProductoActualizar,
    ProductoCrear,
    ProductoRespuesta,
)

router = APIRouter()


# ── Lectura pública del menú (solo productos disponibles) ────────────
@router.get("/", response_model=List[ProductoRespuesta])
def listar_menu(restaurante_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Menú público. Con ?restaurante_id=N devuelve solo el menú de ese restaurante."""
    productos = service.obtener_menu(db, restaurante_id=restaurante_id)
    adjuntar_a_productos(db, productos)
    return productos


@router.get("/categoria/{categoria}", response_model=List[ProductoRespuesta])
def por_categoria(categoria: str, db: Session = Depends(get_db)):
    productos = service.obtener_por_categoria(db, categoria)
    adjuntar_a_productos(db, productos)
    return productos


# ── Gestión (personal del restaurante) ───────────────────────────────
@router.get("/todos", response_model=List[ProductoRespuesta])
def listar_todos(
    restaurante_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(admin_o_empleado),
):
    # Un administrador solo ve (y gestiona) el menú de su propio restaurante
    propio = restaurante_id_de(db, current_user)
    productos = service.obtener_menu(db, solo_disponibles=False, restaurante_id=propio or restaurante_id)
    adjuntar_a_productos(db, productos)
    return productos


@router.post("/", response_model=ProductoRespuesta)
def crear_producto(
    datos: ProductoCrear,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    rid = restaurante_id_de(db, current_user)
    if rid is None:
        raise HTTPException(400, "Tu cuenta no tiene un restaurante asociado")
    producto = service.crear_producto(db, datos, rid)
    auditoria.registrar(
        db, "producto_creado", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="producto", entidad_id=producto.id,
        ip=auditoria.ip_de(request),
    )
    return producto


@router.get("/{producto_id}", response_model=ProductoRespuesta)
def obtener_producto(producto_id: int, db: Session = Depends(get_db)):
    return service.obtener_producto(db, producto_id)


@router.patch("/{producto_id}", response_model=ProductoRespuesta)
def actualizar_producto(
    producto_id: int,
    datos: ProductoActualizar,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    producto = service.actualizar_producto(db, producto_id, datos, restaurante_id_de(db, current_user))
    auditoria.registrar(
        db, "producto_modificado", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="producto", entidad_id=producto_id,
        ip=auditoria.ip_de(request),
    )
    return producto


@router.delete("/{producto_id}")
def eliminar_producto(
    producto_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    resultado = service.eliminar_producto(db, producto_id, restaurante_id_de(db, current_user))
    auditoria.registrar(
        db, "producto_eliminado", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="producto", entidad_id=producto_id,
        ip=auditoria.ip_de(request),
    )
    return resultado
