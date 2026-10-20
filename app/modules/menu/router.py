from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import admin_o_empleado, solo_admin
from app.modules.menu import service
from app.modules.menu.schemas import (
    ProductoActualizar,
    ProductoCrear,
    ProductoRespuesta,
)

router = APIRouter()


# ── Lectura pública del menú (solo productos disponibles) ────────────
@router.get("/", response_model=List[ProductoRespuesta])
def listar_menu(db: Session = Depends(get_db)):
    return service.obtener_menu(db)


@router.get("/categoria/{categoria}", response_model=List[ProductoRespuesta])
def por_categoria(categoria: str, db: Session = Depends(get_db)):
    return service.obtener_por_categoria(db, categoria)


# ── Gestión (personal del restaurante) ───────────────────────────────
@router.get("/todos", response_model=List[ProductoRespuesta])
def listar_todos(
    db: Session = Depends(get_db),
    current_user: dict = Depends(admin_o_empleado),
):
    return service.obtener_menu(db, solo_disponibles=False)


@router.post("/", response_model=ProductoRespuesta)
def crear_producto(
    datos: ProductoCrear,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    return service.crear_producto(db, datos)


@router.get("/{producto_id}", response_model=ProductoRespuesta)
def obtener_producto(producto_id: int, db: Session = Depends(get_db)):
    return service.obtener_producto(db, producto_id)


@router.patch("/{producto_id}", response_model=ProductoRespuesta)
def actualizar_producto(
    producto_id: int,
    datos: ProductoActualizar,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    return service.actualizar_producto(db, producto_id, datos)


@router.delete("/{producto_id}")
def eliminar_producto(
    producto_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    return service.eliminar_producto(db, producto_id)
