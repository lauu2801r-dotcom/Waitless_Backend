from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.modules.menu.models import Producto
from app.modules.menu.schemas import ProductoCrear, ProductoActualizar

def crear_producto(db: Session, datos: ProductoCrear):
    nuevo_producto = Producto(
        nombre=datos.nombre,
        descripcion=datos.descripcion,
        precio=datos.precio,
        categoria=datos.categoria,
        imagen_url=datos.imagen_url
    )
    db.add(nuevo_producto)
    db.commit()
    db.refresh(nuevo_producto)
    return nuevo_producto

def obtener_menu(db: Session, solo_disponibles: bool = True):
    query = db.query(Producto).filter(Producto.activo == True)
    if solo_disponibles:
        query = query.filter(Producto.disponible == True)
    return query.order_by(Producto.categoria, Producto.nombre).all()

def obtener_producto(db: Session, producto_id: int):
    producto = db.query(Producto).filter(
        Producto.id == producto_id,
        Producto.activo == True
    ).first()
    if not producto:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado"
        )
    return producto

def obtener_por_categoria(db: Session, categoria: str):
    return db.query(Producto).filter(
        Producto.categoria == categoria,
        Producto.activo == True,
        Producto.disponible == True
    ).all()

def actualizar_producto(db: Session, producto_id: int, datos: ProductoActualizar):
    producto = obtener_producto(db, producto_id)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(producto, campo, valor)
    db.commit()
    db.refresh(producto)
    return producto

def eliminar_producto(db: Session, producto_id: int):
    producto = obtener_producto(db, producto_id)
    producto.activo = False
    db.commit()
    return {"message": f"Producto {producto.nombre} eliminado"}