from datetime import datetime
from typing import Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.modules.inventario.models import (
    Insumo, MovimientoInventario, Proveedor, TipoMovimiento,
)
from app.modules.inventario.schemas import (
    InsumoActualizar, InsumoCrear, MovimientoCrear,
    ProveedorActualizar, ProveedorCrear, ResumenInventario,
)


def _no_encontrado(que: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{que} no encontrado")


def _redondear(x: float) -> float:
    return round(x, 3)


# ───────────────────────── Proveedores ─────────────────────────
def crear_proveedor(db: Session, datos: ProveedorCrear) -> Proveedor:
    if db.query(Proveedor).filter(Proveedor.nombre.ilike(datos.nombre)).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ya existe un proveedor con ese nombre")
    prov = Proveedor(**datos.model_dump())
    db.add(prov)
    db.commit()
    db.refresh(prov)
    return prov


def listar_proveedores(db: Session, activo: Optional[bool] = True):
    q = db.query(Proveedor)
    if activo is not None:
        q = q.filter(Proveedor.activo == activo)
    return q.order_by(Proveedor.nombre).all()


def obtener_proveedor(db: Session, proveedor_id: int) -> Proveedor:
    prov = db.query(Proveedor).filter(Proveedor.id == proveedor_id).first()
    if not prov:
        raise _no_encontrado("Proveedor")
    return prov


def actualizar_proveedor(db: Session, proveedor_id: int, datos: ProveedorActualizar) -> Proveedor:
    prov = obtener_proveedor(db, proveedor_id)
    cambios = datos.model_dump(exclude_unset=True)
    if "nombre" in cambios and cambios["nombre"] is not None:
        otro = db.query(Proveedor).filter(
            Proveedor.nombre.ilike(cambios["nombre"]), Proveedor.id != proveedor_id
        ).first()
        if otro:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ya existe un proveedor con ese nombre")
    for campo, valor in cambios.items():
        setattr(prov, campo, valor)
    db.commit()
    db.refresh(prov)
    return prov


# ───────────────────────── Insumos ─────────────────────────
def _validar_proveedor(db: Session, proveedor_id: Optional[int]):
    if proveedor_id is not None and not db.query(Proveedor).filter(Proveedor.id == proveedor_id).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El proveedor indicado no existe")


def crear_insumo(db: Session, datos: InsumoCrear, usuario_id: int, email: str) -> Insumo:
    if db.query(Insumo).filter(Insumo.nombre.ilike(datos.nombre)).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ya existe un insumo con ese nombre")
    _validar_proveedor(db, datos.proveedor_id)

    campos = datos.model_dump(exclude={"stock_inicial"})
    insumo = Insumo(**campos, stock_actual=0)
    db.add(insumo)
    db.flush()  # para tener insumo.id

    if datos.stock_inicial > 0:
        insumo.stock_actual = _redondear(datos.stock_inicial)
        db.add(MovimientoInventario(
            insumo_id=insumo.id, tipo=TipoMovimiento.entrada,
            cantidad=insumo.stock_actual, motivo="Stock inicial",
            stock_anterior=0, stock_resultante=insumo.stock_actual,
            usuario_id=usuario_id, usuario_email=email,
        ))
    db.commit()
    db.refresh(insumo)
    return insumo


def listar_insumos(
    db: Session,
    categoria: Optional[str] = None,
    buscar: Optional[str] = None,
    estado: Optional[str] = None,
    activo: Optional[bool] = True,
):
    q = db.query(Insumo).options(joinedload(Insumo.proveedor))
    if activo is not None:
        q = q.filter(Insumo.activo == activo)
    if categoria:
        q = q.filter(Insumo.categoria == categoria)
    if buscar:
        q = q.filter(Insumo.nombre.ilike(f"%{buscar.strip()}%"))
    insumos = q.order_by(Insumo.nombre).all()
    if estado:
        insumos = [i for i in insumos if i.estado == estado]
    return insumos


def obtener_insumo(db: Session, insumo_id: int) -> Insumo:
    insumo = db.query(Insumo).filter(Insumo.id == insumo_id).first()
    if not insumo:
        raise _no_encontrado("Insumo")
    return insumo


def actualizar_insumo(db: Session, insumo_id: int, datos: InsumoActualizar) -> Insumo:
    insumo = obtener_insumo(db, insumo_id)
    cambios = datos.model_dump(exclude_unset=True)
    if cambios.get("nombre"):
        otro = db.query(Insumo).filter(
            Insumo.nombre.ilike(cambios["nombre"]), Insumo.id != insumo_id
        ).first()
        if otro:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ya existe un insumo con ese nombre")
    if "proveedor_id" in cambios:
        _validar_proveedor(db, cambios["proveedor_id"])
    for campo, valor in cambios.items():
        setattr(insumo, campo, valor)
    db.commit()
    db.refresh(insumo)
    return insumo


# ───────────────────────── Movimientos ─────────────────────────
def registrar_movimiento(
    db: Session, datos: MovimientoCrear, usuario_id: int, email: str
) -> Tuple[MovimientoInventario, Insumo, bool]:
    """
    Registra una entrada o salida.
    - Bloquea la fila del insumo mientras se actualiza (evita que dos personas
      saquen al mismo tiempo y el stock quede mal).
    - Impide dejar el stock en negativo.
    Devuelve (movimiento, insumo, hay_alerta).
    """
    insumo = (
        db.query(Insumo).filter(Insumo.id == datos.insumo_id).with_for_update().first()
    )
    if not insumo:
        raise _no_encontrado("Insumo")
    if not insumo.activo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El insumo está desactivado")

    anterior = insumo.stock_actual
    if datos.tipo == TipoMovimiento.entrada:
        nuevo = anterior + datos.cantidad
    else:
        nuevo = anterior - datos.cantidad
        if nuevo < 0:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Stock insuficiente de {insumo.nombre}: hay {_redondear(anterior)} "
                f"{insumo.unidad} y se intentó sacar {_redondear(datos.cantidad)}",
            )
    nuevo = _redondear(nuevo)
    insumo.stock_actual = nuevo

    mov = MovimientoInventario(
        insumo_id=insumo.id, tipo=datos.tipo, cantidad=_redondear(datos.cantidad),
        motivo=datos.motivo, stock_anterior=_redondear(anterior), stock_resultante=nuevo,
        usuario_id=usuario_id, usuario_email=email,
    )
    db.add(mov)
    db.commit()
    db.refresh(mov)
    db.refresh(insumo)

    # Alerta: solo cuando el movimiento lo deja en nivel crítico (agotado o <= mínimo)
    # y antes no estaba ya en ese nivel (para no repetir avisos).
    estaba_ok = anterior > insumo.stock_minimo
    alerta = insumo.estado in ("bajo", "agotado") and estaba_ok
    return mov, insumo, alerta


def listar_movimientos(
    db: Session,
    insumo_id: Optional[int] = None,
    tipo: Optional[TipoMovimiento] = None,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
):
    q = db.query(MovimientoInventario).options(joinedload(MovimientoInventario.insumo))
    if insumo_id is not None:
        q = q.filter(MovimientoInventario.insumo_id == insumo_id)
    if tipo is not None:
        q = q.filter(MovimientoInventario.tipo == tipo)
    if desde is not None:
        q = q.filter(MovimientoInventario.creado_en >= desde)
    if hasta is not None:
        q = q.filter(MovimientoInventario.creado_en <= hasta)
    return (
        q.order_by(MovimientoInventario.creado_en.desc(), MovimientoInventario.id.desc())
        .offset(offset).limit(limit).all()
    )


def resumen(db: Session) -> ResumenInventario:
    insumos = db.query(Insumo).filter(Insumo.activo == True).all()  # noqa: E712
    return ResumenInventario(
        total_insumos=len(insumos),
        bajo_stock=sum(1 for i in insumos if i.estado == "bajo"),
        agotados=sum(1 for i in insumos if i.estado == "agotado"),
        valor_total=round(sum(i.valor for i in insumos), 2),
    )


def alertas(db: Session):
    """Insumos en nivel crítico (bajo o agotado), los más críticos primero."""
    criticos = [i for i in listar_insumos(db) if i.estado in ("bajo", "agotado")]
    return sorted(criticos, key=lambda i: (i.estado != "agotado", i.nombre))
