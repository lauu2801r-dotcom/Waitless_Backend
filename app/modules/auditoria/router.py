import csv
import io
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import solo_admin
from app.modules.auditoria import service
from app.modules.auditoria.schemas import AuditoriaRespuesta

router = APIRouter()


@router.get("/", response_model=List[AuditoriaRespuesta])
def listar_auditoria(
    usuario_id: Optional[int] = None,
    accion: Optional[str] = None,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    q = service.consultar(db, usuario_id, accion, desde, hasta)
    return q.offset(offset).limit(limit).all()


@router.get("/exportar")
def exportar_auditoria_csv(
    usuario_id: Optional[int] = None,
    accion: Optional[str] = None,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    registros = service.consultar(db, usuario_id, accion, desde, hasta).limit(5000).all()

    salida = io.StringIO()
    salida.write("\ufeff")  # BOM para que Excel respete las tildes
    escritor = csv.writer(salida)
    escritor.writerow(
        ["id", "fecha", "usuario_id", "email", "accion", "entidad", "entidad_id", "detalle", "ip"]
    )
    for r in registros:
        escritor.writerow(
            [r.id, r.creado_en, r.usuario_id, r.email, r.accion,
             r.entidad, r.entidad_id, r.detalle, r.ip]
        )
    salida.seek(0)

    return StreamingResponse(
        iter([salida.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=auditoria.csv"},
    )
