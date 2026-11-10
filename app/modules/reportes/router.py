from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import restaurante_id_de, restaurante_requerido, solo_admin
from app.modules.auditoria import service as auditoria
from app.modules.reportes import exportar, service
from app.modules.reportes.schemas import DashboardRespuesta

router = APIRouter()


@router.get("/dashboard", response_model=DashboardRespuesta)
def dashboard(
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    return service.obtener_dashboard(db, restaurante_id_de(db, current_user))


# ───────────────────────── Exportar (solo administrador) ─────────────────────────
def _validar_fechas(desde: Optional[date], hasta: Optional[date]):
    if desde and hasta and desde > hasta:
        raise HTTPException(400, "La fecha 'desde' no puede ser posterior a 'hasta'")


def _descarga(contenido: bytes, nombre: str, tipo: str, request: Request, db: Session, user: dict):
    auditoria.registrar(
        db, "reporte_exportado", usuario_id=int(user["sub"]), email=user["email"],
        entidad="reporte", detalle=nombre, ip=auditoria.ip_de(request),
    )
    return Response(
        content=contenido, media_type=tipo,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.get("/ventas.csv")
def ventas_csv(
    request: Request,
    desde: Optional[date] = Query(None, description="AAAA-MM-DD (hora Colombia)"),
    hasta: Optional[date] = Query(None, description="AAAA-MM-DD, incluye ese día"),
    db: Session = Depends(get_db), current_user: dict = Depends(solo_admin),
):
    _validar_fechas(desde, hasta)
    rid = restaurante_requerido(db, current_user)
    return _descarga(
        exportar.ventas_csv(db, rid, desde, hasta),
        f"waitless_ventas_{date.today():%Y-%m-%d}.csv", "text/csv; charset=utf-8",
        request, db, current_user,
    )


@router.get("/inventario.csv")
def inventario_csv(
    request: Request,
    db: Session = Depends(get_db), current_user: dict = Depends(solo_admin),
):
    rid = restaurante_requerido(db, current_user)
    return _descarga(
        exportar.inventario_csv(db, rid),
        f"waitless_inventario_{date.today():%Y-%m-%d}.csv", "text/csv; charset=utf-8",
        request, db, current_user,
    )


@router.get("/calificaciones.csv")
def calificaciones_csv(
    request: Request,
    desde: Optional[date] = None, hasta: Optional[date] = None,
    db: Session = Depends(get_db), current_user: dict = Depends(solo_admin),
):
    _validar_fechas(desde, hasta)
    rid = restaurante_requerido(db, current_user)
    return _descarga(
        exportar.calificaciones_csv(db, rid, desde, hasta),
        f"waitless_calificaciones_{date.today():%Y-%m-%d}.csv", "text/csv; charset=utf-8",
        request, db, current_user,
    )


@router.get("/resumen.pdf")
def resumen_pdf(
    request: Request,
    desde: Optional[date] = None, hasta: Optional[date] = None,
    db: Session = Depends(get_db), current_user: dict = Depends(solo_admin),
):
    _validar_fechas(desde, hasta)
    rid = restaurante_requerido(db, current_user)
    return _descarga(
        exportar.resumen_pdf(db, rid, desde, hasta),
        f"waitless_resumen_{date.today():%Y-%m-%d}.pdf", "application/pdf",
        request, db, current_user,
    )
