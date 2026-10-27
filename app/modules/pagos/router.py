from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import admin_o_empleado, es_personal, get_current_user, restaurante_id_de, solo_admin
from app.modules.auditoria import service as auditoria
from app.modules.pagos import service
from app.modules.notificaciones import service as notificaciones
from app.modules.pagos.models import EstadoFactura, MetodoPago
from app.modules.pagos.schemas import (
    AnularFactura, FacturaDetalle, FacturaResumen, PagoCrear, PagoRespuesta,
    PedidoPorCobrar, ResumenVentas,
)
from app.websocket.manager import manager

router = APIRouter()


@router.post("/", response_model=PagoRespuesta)
def pagar(
    datos: PagoCrear, request: Request, tareas: BackgroundTasks,
    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user),
):
    """
    Paga un pedido. Si la pasarela (simulada) lo aprueba se genera la factura y
    se envía por correo. Si lo rechaza, responde con estado "rechazado" y el
    motivo: se puede volver a llamar a este mismo endpoint para reintentar.
    """
    uid, email = int(current_user["sub"]), current_user["email"]
    pago, factura = service.pagar(db, datos, uid, email, current_user["rol"])
    auditoria.registrar(
        db, f"pago_{pago.estado.value}", usuario_id=uid, email=email,
        entidad="pedido", entidad_id=pago.pedido_id,
        detalle=f"{pago.metodo.value} ${pago.monto:,.0f}" + (f" · {factura.numero}" if factura else f" · {pago.motivo_rechazo}"),
        ip=auditoria.ip_de(request),
    )
    notificaciones.avisar_pago(db, pago, factura)
    if factura is not None:
        evento = {
            "tipo": "pago_aprobado", "pedido_id": pago.pedido_id,
            "factura": factura.numero, "total": factura.total,
            "mensaje": f"Pago aprobado · {factura.numero}",
        }
        manager.emitir("dashboard", evento)
        manager.emitir("pedidos", evento)
        manager.emitir(f"usuario:{factura.usuario_id}", evento)
        tareas.add_task(service.enviar_factura_email, factura.id)
    respuesta = PagoRespuesta.model_validate(pago)
    if factura is not None:
        respuesta.factura = FacturaResumen.model_validate(factura)
    return respuesta


@router.get("/mis-facturas", response_model=List[FacturaResumen])
def mis_facturas(
    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user),
):
    return service.listar_facturas(db, usuario_id=int(current_user["sub"]))


@router.get("/facturas", response_model=List[FacturaResumen])
def listar_facturas(
    estado: Optional[EstadoFactura] = None,
    metodo: Optional[MetodoPago] = None,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), current_user: dict = Depends(admin_o_empleado),
):
    return service.listar_facturas(
        db, None, estado, metodo, desde, hasta, limit, offset,
        restaurante_id=restaurante_id_de(db, current_user),
    )


@router.get("/facturas/{factura_id}", response_model=FacturaDetalle)
def obtener_factura(
    factura_id: int, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    f = service.obtener_factura(db, factura_id)
    if not es_personal(current_user) and f.usuario_id != int(current_user["sub"]):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para ver esta factura")
    return f


@router.post("/facturas/{factura_id}/anular", response_model=FacturaDetalle)
def anular_factura(
    factura_id: int, datos: AnularFactura, request: Request,
    db: Session = Depends(get_db), current_user: dict = Depends(solo_admin),
):
    f = service.anular_factura(db, factura_id, datos.motivo, current_user["email"])
    auditoria.registrar(
        db, "factura_anulada", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="factura", entidad_id=factura_id,
        detalle=f"{f.numero}: {datos.motivo}", ip=auditoria.ip_de(request),
    )
    manager.emitir("dashboard", {
        "tipo": "factura_anulada", "factura": f.numero, "mensaje": f"Factura {f.numero} anulada",
    })
    notificaciones.avisar_factura_anulada(db, f, datos.motivo)
    return f


@router.get("/resumen", response_model=ResumenVentas)
def resumen(
    periodo: str = Query("hoy", pattern="^(hoy|semana|mes|anio)$"),
    db: Session = Depends(get_db), current_user: dict = Depends(solo_admin),
):
    return service.resumen(db, periodo, restaurante_id_de(db, current_user))


@router.get("/por-cobrar", response_model=List[PedidoPorCobrar])
def por_cobrar(db: Session = Depends(get_db), current_user: dict = Depends(admin_o_empleado)):
    return service.por_cobrar(db, restaurante_id_de(db, current_user))


@router.get("/pedido/{pedido_id}", response_model=List[PagoRespuesta])
def pagos_del_pedido(
    pedido_id: int, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Intentos de pago de un pedido (para mostrar el historial y reintentar)."""
    from app.modules.pedidos.models import Pedido

    pedido = db.query(Pedido).filter(Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pedido no encontrado")
    if not es_personal(current_user) and pedido.usuario_id != int(current_user["sub"]):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para ver estos pagos")
    return service.pagos_de_pedido(db, pedido_id)
