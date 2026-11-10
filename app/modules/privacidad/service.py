"""
Derechos del titular de datos personales (Ley 1581 de 2012):
  · acceso      → exportar() devuelve todo lo que el sistema guarda de la persona
  · supresión   → eliminar_cuenta() anonimiza la cuenta y borra lo que no hay obligación de conservar

Lo que SÍ se conserva (sin datos personales): pedidos, pagos y facturas, porque son registros
contables del restaurante, y las estrellas de las calificaciones (sin comentario).
"""
import json
import secrets
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_password_hash, verify_password
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.auth.models import RolUsuario, Usuario
from app.modules.calificaciones.models import Calificacion
from app.modules.clientes.models import Favorito
from app.modules.mesas.models import EstadoMesa
from app.modules.notificaciones.models import Notificacion
from app.modules.pagos.models import Factura, Pago
from app.modules.pedidos.models import Pedido
from app.modules.reservas.models import EstadoReserva, Reserva

FRASE_CONFIRMACION = "ELIMINAR"


def _f(d: Optional[datetime]) -> Optional[str]:
    return d.isoformat() if d else None


def _v(x):
    return getattr(x, "value", x)


def exportar(db: Session, usuario_id: int) -> dict:
    u = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    reservas = db.query(Reserva).filter(Reserva.usuario_id == usuario_id).order_by(Reserva.id).all()
    pedidos = db.query(Pedido).filter(Pedido.usuario_id == usuario_id).order_by(Pedido.id).all()
    facturas = db.query(Factura).filter(Factura.usuario_id == usuario_id).order_by(Factura.id).all()
    cals = db.query(Calificacion).filter(Calificacion.usuario_id == usuario_id).order_by(Calificacion.id).all()
    return {
        "generado_en": datetime.utcnow().isoformat() + "Z",
        "perfil": {
            "nombre": u.nombre, "apellido": u.apellido, "email": u.email, "telefono": u.telefono,
            "rol": _v(u.rol), "cargo": u.cargo, "creado_en": _f(u.creado_en),
            "politica_version_aceptada": u.politica_version,
            "politica_aceptada_en": _f(u.politica_aceptada_en),
        },
        "reservas": [
            {"id": r.id, "mesa": r.mesa.numero if r.mesa else None, "fecha_hora": _f(r.fecha_hora),
             "personas": r.numero_personas, "estado": _v(r.estado), "notas": r.notas,
             "motivo_cancelacion": r.motivo_cancelacion}
            for r in reservas
        ],
        "pedidos": [
            {"id": p.id, "creado_en": _f(p.creado_en), "estado": _v(p.estado), "total": p.total,
             "restaurante": p.restaurante_nombre, "notas": p.notas,
             "direccion_domicilio": p.direccion_domicilio}
            for p in pedidos
        ],
        "facturas": [
            {"numero": f.numero, "pedido_id": f.pedido_id, "total": f.total, "metodo": _v(f.metodo),
             "estado": _v(f.estado), "pagado_en": _f(f.pagado_en)}
            for f in facturas
        ],
        "calificaciones": [
            {"pedido_id": c.pedido_id, "estrellas": c.estrellas, "comentario": c.comentario,
             "creado_en": _f(c.creado_en)}
            for c in cals
        ],
        "favoritos": [f.producto.nombre for f in db.query(Favorito).filter(Favorito.usuario_id == usuario_id).all()
                      if f.producto],
        "notificaciones_guardadas": db.query(Notificacion).filter(Notificacion.usuario_id == usuario_id).count(),
    }


def eliminar_cuenta(db: Session, usuario_id: int, password: str, confirmacion: str) -> str:
    u = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    if (confirmacion or "").strip().upper() != FRASE_CONFIRMACION:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f'Escribe "{FRASE_CONFIRMACION}" para confirmar')
    if not verify_password(password or "", u.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La contraseña no es correcta")
    if u.rol == RolUsuario.administrador:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Tu cuenta administra un restaurante y no se puede eliminar desde la app. "
            "Solicítalo al equipo de WaitLess para transferir o cerrar el restaurante.",
        )

    anonimo = f"eliminado-{u.id}@anonimo.invalid"

    # 1) Reservas vigentes: se cancelan y se liberan las mesas
    for r in db.query(Reserva).filter(
        Reserva.usuario_id == u.id,
        Reserva.estado.in_([EstadoReserva.pendiente, EstadoReserva.confirmada]),
    ).all():
        r.estado = EstadoReserva.cancelada
        r.motivo_cancelacion = "Cuenta eliminada por el titular"
        if r.mesa and r.mesa.estado == EstadoMesa.reservada:
            r.mesa.estado = EstadoMesa.libre
    # las notas de reservas pasadas pueden tener datos personales
    for r in db.query(Reserva).filter(Reserva.usuario_id == u.id).all():
        r.notas = None

    # 2) Lo que no hay que conservar se borra
    db.query(Notificacion).filter(Notificacion.usuario_id == u.id).delete(synchronize_session=False)
    db.query(Favorito).filter(Favorito.usuario_id == u.id).delete(synchronize_session=False)
    for c in db.query(Calificacion).filter(Calificacion.usuario_id == u.id).all():
        c.comentario = None
    for p in db.query(Pedido).filter(Pedido.usuario_id == u.id).all():
        p.direccion_domicilio = None
        p.notas = None

    # 3) Registros contables: se conservan sin datos de contacto
    for f in db.query(Factura).filter(Factura.usuario_id == u.id).all():
        if f.detalle:
            try:
                d = json.loads(f.detalle)
                if isinstance(d, dict):
                    for k in ("cliente_email", "cliente_nombre", "cliente"):
                        if k in d:
                            d[k] = None
                    f.detalle = json.dumps(d, ensure_ascii=False)
            except (ValueError, TypeError):
                pass
    db.query(Pago).filter(Pago.usuario_id == u.id).update({Pago.usuario_email: anonimo}, synchronize_session=False)
    db.query(RegistroAuditoria).filter(RegistroAuditoria.usuario_id == u.id).update(
        {RegistroAuditoria.email: anonimo}, synchronize_session=False
    )

    # 4) La cuenta queda anonimizada e inutilizable
    u.nombre, u.apellido, u.email, u.telefono = "Usuario", "eliminado", anonimo, None
    u.hashed_password = get_password_hash(secrets.token_urlsafe(32))
    u.activo = False
    u.verificado = False
    u.otp_code = None
    u.otp_expira = None
    u.restaurante_id = None
    u.cargo = None
    db.commit()
    return anonimo
