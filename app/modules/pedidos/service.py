from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status
from app.modules.pedidos.models import Pedido, ItemPedido, EstadoPedido, TipoEntrega
from app.modules.auth.models import Restaurante
from app.modules.restaurantes import horarios as horarios_mod
from app.modules.pedidos.schemas import PedidoCrear, PedidoActualizar, PedidoEditarItems
from app.modules.menu.models import Producto
from app.modules.mesas.models import Mesa, EstadoMesa

def _dinero(v: float) -> str:
    return "$" + f"{round(v):,}".replace(",", ".")


def _config_domicilio(restaurante) -> tuple[bool, int, int]:
    """(activo, costo de envío, pedido mínimo) con los valores por defecto."""
    activo = True if restaurante.domicilio_activo is None else bool(restaurante.domicilio_activo)
    costo = 5000 if restaurante.costo_domicilio is None else int(restaurante.costo_domicilio)
    minimo = int(restaurante.pedido_minimo_domicilio or 0)
    return activo, costo, minimo


def crear_pedido(db: Session, datos: PedidoCrear, usuario_id: int):
    es_domicilio = datos.tipo_entrega == TipoEntrega.domicilio

    mesa = None
    if not es_domicilio:
        mesa = db.query(Mesa).filter(
            Mesa.id == datos.mesa_id,
            Mesa.activa == True
        ).first()
        if not mesa:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mesa no encontrada"
            )

    total = 0.0
    items_data = []
    restaurantes_pedido = set()

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

        restaurantes_pedido.add(producto.restaurante_id)
        subtotal = producto.precio * item.cantidad
        total += subtotal

        items_data.append(ItemPedido(
            producto_id=item.producto_id,
            cantidad=item.cantidad,
            precio_unitario=producto.precio,
            subtotal=subtotal,
            notas=item.notas
        ))

    if len(restaurantes_pedido) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un pedido solo puede tener platos de un mismo restaurante"
        )
    restaurante_id = next(iter(restaurantes_pedido), None)
    if mesa is not None and restaurante_id is not None and mesa.restaurante_id is not None and mesa.restaurante_id != restaurante_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La mesa no pertenece al restaurante de los platos elegidos"
        )

    costo_envio = 0.0
    if es_domicilio:
        restaurante = db.query(Restaurante).filter(Restaurante.id == restaurante_id).first() if restaurante_id else None
        if restaurante is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "No se pudo identificar el restaurante del domicilio")
        activo, costo, minimo = _config_domicilio(restaurante)
        if not activo:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{restaurante.nombre} no tiene servicio a domicilio por ahora")
        abierto, mensaje = horarios_mod.estado_en(restaurante.horarios, horarios_mod.ahora_colombia())
        if abierto is False:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{mensaje}. No se puede pedir a domicilio ahora.")
        if minimo and total < minimo:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"El pedido mínimo para domicilio es {_dinero(minimo)}. Te faltan {_dinero(minimo - total)}.",
            )
        costo_envio = float(costo)

    nuevo_pedido = Pedido(
        usuario_id=usuario_id,
        restaurante_id=restaurante_id or (mesa.restaurante_id if mesa else None),
        mesa_id=None if es_domicilio else datos.mesa_id,
        reserva_id=None if es_domicilio else datos.reserva_id,
        notas=datos.notas,
        total=total + costo_envio,
        items=items_data,
        tipo_entrega=TipoEntrega.domicilio if es_domicilio else TipoEntrega.restaurante,
        direccion_domicilio=(datos.direccion_domicilio or "").strip() if es_domicilio else None,
        telefono_contacto=(datos.telefono_contacto or "").strip() if es_domicilio else None,
        indicaciones_domicilio=((datos.indicaciones_domicilio or "").strip() or None) if es_domicilio else None,
        costo_envio=costo_envio,
    )

    if mesa is not None:
        mesa.estado = EstadoMesa.ocupada

    db.add(nuevo_pedido)
    db.commit()
    db.refresh(nuevo_pedido)
    return nuevo_pedido

def obtener_pedidos_usuario(db: Session, usuario_id: int):
    return db.query(Pedido).options(
        joinedload(Pedido.items).joinedload(ItemPedido.producto)
    ).filter(
        Pedido.usuario_id == usuario_id
    ).order_by(Pedido.creado_en.desc()).all()

def obtener_todos_pedidos(db: Session, restaurante_id: Optional[int] = None):
    q = db.query(Pedido).options(
        joinedload(Pedido.items).joinedload(ItemPedido.producto)
    )
    if restaurante_id is not None:
        q = q.filter(Pedido.restaurante_id == restaurante_id)
    return q.order_by(Pedido.creado_en.desc()).all()

def obtener_pedidos_activos(db: Session, restaurante_id: Optional[int] = None):
    q = db.query(Pedido).options(
        joinedload(Pedido.items).joinedload(ItemPedido.producto)
    ).filter(
        Pedido.estado.in_([
            EstadoPedido.pendiente,
            EstadoPedido.en_preparacion
        ])
    )
    if restaurante_id is not None:
        q = q.filter(Pedido.restaurante_id == restaurante_id)
    return q.order_by(Pedido.creado_en.asc()).all()

def obtener_pedido(db: Session, pedido_id: int):
    pedido = db.query(Pedido).options(
        joinedload(Pedido.items).joinedload(ItemPedido.producto)
    ).filter(
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

    # Momento real en que la cocina terminó (alimenta y evalúa la IA)
    if datos.estado in (EstadoPedido.listo, EstadoPedido.entregado) and pedido.listo_en is None:
        pedido.listo_en = datetime.now(timezone.utc).replace(tzinfo=None)

    if datos.estado == EstadoPedido.entregado and pedido.mesa_id is not None:
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

def editar_items_pedido(db: Session, pedido_id: int, usuario_id: int, datos: PedidoEditarItems):
    pedido = obtener_pedido(db, pedido_id)

    if pedido.usuario_id != usuario_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para editar este pedido"
        )

    if pedido.estado != EstadoPedido.pendiente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se pueden editar pedidos en estado pendiente"
        )

    for item in pedido.items:
        db.delete(item)

    total = 0.0
    nuevos_items = []

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

        nuevos_items.append(ItemPedido(
            pedido_id=pedido_id,
            producto_id=item.producto_id,
            cantidad=item.cantidad,
            precio_unitario=producto.precio,
            subtotal=subtotal,
            notas=item.notas
        ))

    pedido.items = nuevos_items
    # El tipo de entrega no cambia al editar; en domicilio se conserva el envío ya cobrado
    envio = float(pedido.costo_envio or 0) if pedido.tipo_entrega == TipoEntrega.domicilio else 0.0
    pedido.total = total + envio
    pedido.notas = datos.notas
    if pedido.tipo_entrega == TipoEntrega.domicilio:
        if datos.direccion_domicilio and len(datos.direccion_domicilio.strip()) >= 8:
            pedido.direccion_domicilio = datos.direccion_domicilio.strip()
        if datos.telefono_contacto:
            pedido.telefono_contacto = datos.telefono_contacto.strip()
        if datos.indicaciones_domicilio is not None:
            pedido.indicaciones_domicilio = datos.indicaciones_domicilio.strip() or None

    db.commit()
    db.refresh(pedido)
    return pedido