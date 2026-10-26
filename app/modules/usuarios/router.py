from typing import List, Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import restaurante_id_de, solo_admin
from app.modules.auditoria import service as auditoria
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
    empleado = service.crear_empleado(db, datos, restaurante_id_de(db, current_user))
    auditoria.registrar(
        db, "empleado_creado", usuario_id=int(current_user["sub"]),
        email=current_user["email"], entidad="usuario", entidad_id=empleado.id,
        detalle=f"empleado: {empleado.email}", ip=auditoria.ip_de(request),
    )
    return empleado


@router.get("/", response_model=List[UsuarioGestionRespuesta])
def listar_usuarios(
    activo: Optional[bool] = None,
    buscar: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    """Personal del restaurante del administrador (solo sus empleados)."""
    return service.listar_usuarios(db, restaurante_id_de(db, current_user), activo, buscar)


@router.get("/{usuario_id}", response_model=UsuarioGestionRespuesta)
def obtener_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    return service.obtener_usuario(db, usuario_id, restaurante_id_de(db, current_user))


@router.patch("/{usuario_id}", response_model=UsuarioGestionRespuesta)
def actualizar_usuario(
    usuario_id: int,
    datos: UsuarioActualizar,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_admin),
):
    usuario, cambios = service.actualizar_usuario(
        db, usuario_id, datos, int(current_user["sub"]),
        restaurante_id_de(db, current_user),
    )
    if cambios:
        auditoria.registrar(
            db, "usuario_modificado", usuario_id=int(current_user["sub"]),
            email=current_user["email"], entidad="usuario", entidad_id=usuario_id,
            detalle="; ".join(cambios), ip=auditoria.ip_de(request),
        )
    return usuario
