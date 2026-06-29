from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.modules.menu import service
from app.modules.menu.schemas import (
    ProductoCrear,
    ProductoActualizar,
    ProductoRespuesta
)

router = APIRouter()

@router.post("/", response_model=ProductoRespuesta)
def crear_producto(datos: ProductoCrear, db: Session = Depends(get_db)):
    return service.crear_producto(db, datos)

@router.get("/", response_model=List[ProductoRespuesta])
def listar_menu(db: Session = Depends(get_db)):
    return service.obtener_menu(db)

@router.get("/todos", response_model=List[ProductoRespuesta])
def listar_todos(db: Session = Depends(get_db)):
    return service.obtener_menu(db, solo_disponibles=False)

@router.get("/categoria/{categoria}", response_model=List[ProductoRespuesta])
def por_categoria(categoria: str, db: Session = Depends(get_db)):
    return service.obtener_por_categoria(db, categoria)

@router.get("/{producto_id}", response_model=ProductoRespuesta)
def obtener_producto(producto_id: int, db: Session = Depends(get_db)):
    return service.obtener_producto(db, producto_id)

@router.patch("/{producto_id}", response_model=ProductoRespuesta)
def actualizar_producto(
    producto_id: int,
    datos: ProductoActualizar,
    db: Session = Depends(get_db)
):
    return service.actualizar_producto(db, producto_id, datos)

@router.delete("/{producto_id}")
def eliminar_producto(producto_id: int, db: Session = Depends(get_db)):
    return service.eliminar_producto(db, producto_id)