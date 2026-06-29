from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.modules.mesas.models import Mesa, EstadoMesa
from app.modules.mesas.schemas import MesaCrear, MesaActualizar

def crear_mesa(db: Session, datos: MesaCrear):
    mesa_existente = db.query(Mesa).filter(
        Mesa.numero == datos.numero
    ).first()
    
    if mesa_existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ya existe una mesa con el número {datos.numero}"
        )
    
    nueva_mesa = Mesa(
        numero=datos.numero,
        capacidad=datos.capacidad,
        ubicacion=datos.ubicacion
    )
    db.add(nueva_mesa)
    db.commit()
    db.refresh(nueva_mesa)
    return nueva_mesa

def obtener_mesas(db: Session, solo_activas: bool = True):
    query = db.query(Mesa)
    if solo_activas:
        query = query.filter(Mesa.activa == True)
    return query.order_by(Mesa.numero).all()

def obtener_mesa(db: Session, mesa_id: int):
    mesa = db.query(Mesa).filter(Mesa.id == mesa_id).first()
    if not mesa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mesa no encontrada"
        )
    return mesa

def actualizar_mesa(db: Session, mesa_id: int, datos: MesaActualizar):
    mesa = obtener_mesa(db, mesa_id)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(mesa, campo, valor)
    db.commit()
    db.refresh(mesa)
    return mesa

def actualizar_estado_mesa(db: Session, mesa_id: int, estado: EstadoMesa):
    mesa = obtener_mesa(db, mesa_id)
    mesa.estado = estado
    db.commit()
    db.refresh(mesa)
    return mesa

async def actualizar_estado_mesa_ws(db: Session, mesa_id: int, estado: EstadoMesa):
    from app.websocket.manager import manager
    mesa = obtener_mesa(db, mesa_id)
    mesa.estado = estado
    db.commit()
    db.refresh(mesa)
    
    await manager.broadcast("mesas", {
        "tipo": "estado_mesa",
        "mesa_id": mesa_id,
        "numero": mesa.numero,
        "estado": estado,
        "mensaje": f"Mesa {mesa.numero} cambió a {estado}"
    })
    
    await manager.broadcast("dashboard", {
        "tipo": "actualizacion_mesa",
        "mesa_id": mesa_id,
        "estado": estado
    })
    
    return mesa

def eliminar_mesa(db: Session, mesa_id: int):
    mesa = obtener_mesa(db, mesa_id)
    mesa.activa = False
    db.commit()
    return {"message": f"Mesa {mesa.numero} desactivada"}

def obtener_mesas_disponibles(db: Session):
    return db.query(Mesa).filter(
        Mesa.estado == EstadoMesa.libre,
        Mesa.activa == True
    ).order_by(Mesa.numero).all()