from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.modules.pedidos.models import Pedido, ItemPedido, EstadoPedido
from app.modules.pedidos.schemas import PedidoCrear, PedidoActualizar
from app.modules.menu.models import Producto
from app.modules.mesas.models import Mesa, EstadoMesa

def crear_pedido(db: Session, datos: PedidoCrear, usuario_id: int):
    # Verificar mesa
    mesa = db.query(Mesa).filter(
        Mesa.id == datos.mesa_id,
        Mesa.activa == True
    ).first()
    
    if not mesa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mesa no encontrada"
        )
    
    # Calcular total y crear items
    total = 0.0
    items_data = []
    
    for item in datos.items:
        producto = db.query(Producto).filter(
            Producto.id == item.producto_id,
            Producto.activo == True,
            Producto.disponible == True
        ).first()
        
        if not producto:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Producto {item.producto_id} no encontrado o no disponible"
            )
        
        subtotal = producto.precio * item.cantidad
        total += subtotal
        
        items_data.append(ItemPedido(
            producto_id=item.producto_id,
            cantidad=item.cantidad,
            precio_unitario=producto.precio,
            subtotal=subtotal,
            notas=item.notas
        ))
    
    # Crear pedido
    nuevo_pedido = Pedido(
        usuario_id=usuario_id,
        mesa_id=datos.mesa_id,
        reserva_id=datos.reserva_id,
        notas=datos.notas,
        total=total,
        items=items_data
    )
    
    # Actualizar estado mesa a ocupada
    mesa.estado = EstadoMesa.ocupada
    
    db.add(nuevo_pedido)
    db.commit()
    db.refresh(nuevo_pedido)
    return nuevo_pedido

def obtener_pedidos_usuario(db: Session, usuario_id: int):
    return db.query(Pedido).filter(
        Pedido.usuario_id == usuario_id
    ).order_by(Pedido.creado_en.desc()).all()

def obtener_todos_pedidos(db: Session):
    return db.query(Pedido).order_by(
        Pedido.creado_en.desc()
    ).all()

def obtener_pedidos_activos(db: Session):
    return db.query(Pedido).filter(
        Pedido.estado.in_([
            EstadoPedido.pendiente,
            EstadoPedido.en_preparacion
        ])
    ).order_by(Pedido.creado_en.asc()).all()

def obtener_pedido(db: Session, pedido_id: int):
    pedido = db.query(Pedido).filter(
        Pedido.id == pedido_id
    ).first()
    if not pedido:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pedido no encontrado"
        )
    return pedido

def actualizar_estado_pedido(db: Session, pedido_id: int, datos: PedidoActualizar):
    pedido = obtener_pedido(db, pedido_id)
    
    if pedido.estado == EstadoPedido.cancelado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede modificar un pedido cancelado"
        )
    
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(pedido, campo, valor)
    
    # Si el pedido se entrega liberar la mesa
    if datos.estado == EstadoPedido.entregado:
        mesa = db.query(Mesa).filter(Mesa.id == pedido.mesa_id).first()
        if mesa:
            mesa.estado = EstadoMesa.en_limpieza
    
    db.commit()
    db.refresh(pedido)
    return pedido

def cancelar_pedido(db: Session, pedido_id: int, usuario_id: int):
    pedido = obtener_pedido(db, pedido_id)
    
    if pedido.usuario_id != usuario_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para cancelar este pedido"
        )
    
    if pedido.estado not in [EstadoPedido.pendiente]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se pueden cancelar pedidos en estado pendiente"
        )
    
    pedido.estado = EstadoPedido.cancelado
    db.commit()
    return {"message": "Pedido cancelado exitosamente"}