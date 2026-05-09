from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from datetime import datetime
from app.modules.reservas.models import Reserva, EstadoReserva
from app.modules.reservas.schemas import ReservaCrear, ReservaActualizar
from app.modules.mesas.models import Mesa, EstadoMesa

def crear_reserva(db: Session, datos: ReservaCrear, usuario_id: int):
    # Verificar que la mesa existe
    mesa = db.query(Mesa).filter(
        Mesa.id == datos.mesa_id,
        Mesa.activa == True
    ).first()
    
    if not mesa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mesa no encontrada"
        )
    
    if mesa.estado not in [EstadoMesa.libre]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La mesa no está disponible. Estado actual: {mesa.estado}"
        )
    
    if datos.numero_personas > mesa.capacidad:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La mesa tiene capacidad para {mesa.capacidad} personas"
        )
    
    # Crear reserva
    nueva_reserva = Reserva(
        usuario_id=usuario_id,
        mesa_id=datos.mesa_id,
        fecha_hora=datos.fecha_hora,
        numero_personas=datos.numero_personas,
        notas=datos.notas,
        tiempo_espera_estimado=15
    )
    
    # Actualizar estado de la mesa
    mesa.estado = EstadoMesa.reservada
    
    db.add(nueva_reserva)
    db.commit()
    db.refresh(nueva_reserva)
    return nueva_reserva

def obtener_reservas(db: Session, usuario_id: int):
    return db.query(Reserva).filter(
        Reserva.usuario_id == usuario_id
    ).order_by(Reserva.fecha_hora.desc()).all()

def obtener_todas_reservas(db: Session):
    return db.query(Reserva).order_by(
        Reserva.fecha_hora.desc()
    ).all()

def obtener_reserva(db: Session, reserva_id: int):
    reserva = db.query(Reserva).filter(
        Reserva.id == reserva_id
    ).first()
    if not reserva:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reserva no encontrada"
        )
    return reserva

def actualizar_reserva(db: Session, reserva_id: int, datos: ReservaActualizar, usuario_id: int):
    reserva = obtener_reserva(db, reserva_id)
    
    if reserva.usuario_id != usuario_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para modificar esta reserva"
        )
    
    if reserva.estado == EstadoReserva.cancelada:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede modificar una reserva cancelada"
        )
    
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(reserva, campo, valor)
    
    db.commit()
    db.refresh(reserva)
    return reserva

def cancelar_reserva(db: Session, reserva_id: int, usuario_id: int):
    reserva = obtener_reserva(db, reserva_id)
    
    if reserva.usuario_id != usuario_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para cancelar esta reserva"
        )
    
    if reserva.estado == EstadoReserva.cancelada:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La reserva ya está cancelada"
        )
    
    # Liberar la mesa
    mesa = db.query(Mesa).filter(Mesa.id == reserva.mesa_id).first()
    if mesa:
        mesa.estado = EstadoMesa.libre
    
    reserva.estado = EstadoReserva.cancelada
    db.commit()
    return {"message": "Reserva cancelada exitosamente"}