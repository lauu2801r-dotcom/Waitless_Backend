from typing import List, Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import solo_admin
from app.modules.auditoria import service as auditoria
from app.modules.auth.models import RolUsuario
from app.modules.usuarios import service
from app.modules.usuarios.schemas import (
    EmpleadoCrear,
    UsuarioActualizar,
    UsuarioGestionRespuesta,
)

router = APIRouter()


@router.post("/empleados", response_model=UsuarioGestionRespuesta)
def crear_empleado(
    datos: EmpleadoCrear,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    empleado = service.crear_empleado(db, datos)
    auditoria.registrar(
        db, "empleado_creado", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="usuario", entidad_id=empleado.id,
        detalle=f"empleado: {empleado.email}", ip=auditoria.ip_de(request),
    )
    return empleado


@router.get("/", response_model=List[UsuarioGestionRespuesta])
def listar_usuarios(
    rol: Optional[RolUsuario] = None,
    activo: Optional[bool] = None,
    buscar: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    return service.listar_usuarios(db, rol, activo, buscar)


@router.get("/{usuario_id}", response_model=UsuarioGestionRespuesta)
def obtener_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    return service.obtener_usuario(db, usuario_id)


@router.patch("/{usuario_id}", response_model=UsuarioGestionRespuesta)
def actualizar_usuario(
    usuario_id: int,
    datos: UsuarioActualizar,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    usuario, cambios = service.actualizar_usuario(
        db, usuario_id, datos, int(current_user["sub"])
    )
    if cambios:
        auditoria.registrar(
            db, "usuario_modificado", usuario_id=int(current_user["sub"]),
            email=current_user["email"], entidad="usuario", entidad_id=usuario_id,
            detalle="; ".join(cambios), ip=auditoria.ip_de(request),
        )
    return usuario
