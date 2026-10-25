from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.modules.auth.models import RolUsuario, Usuario
from app.modules.usuarios.schemas import EmpleadoCrear, UsuarioActualizar


def crear_empleado(db: Session, datos: EmpleadoCrear) -> Usuario:
    email = datos.email.lower().strip()
    if db.query(Usuario).filter(Usuario.email == email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe una cuenta con ese correo",
        )

    # El administrador responde por la identidad del empleado, por eso la
    # cuenta nace verificada (no pasa por el código OTP).
    empleado = Usuario(
        nombre=datos.nombre.strip(),
        apellido=datos.apellido.strip(),
        email=email,
        telefono=datos.telefono,
        hashed_password=get_password_hash(datos.password),
        rol=RolUsuario.empleado,
        verificado=True,
        activo=True,
    )
    db.add(empleado)
    db.commit()
    db.refresh(empleado)
    return empleado


def listar_usuarios(
    db: Session,
    rol: Optional[RolUsuario] = None,
    activo: Optional[bool] = None,
    buscar: Optional[str] = None,
):
    q = db.query(Usuario)
    if rol is not None:
        q = q.filter(Usuario.rol == rol)
    if activo is not None:
        q = q.filter(Usuario.activo == activo)
    if buscar:
        patron = f"%{buscar.strip()}%"
        q = q.filter(
            or_(
                Usuario.nombre.ilike(patron),
                Usuario.apellido.ilike(patron),
                Usuario.email.ilike(patron),
            )
        )
    return q.order_by(Usuario.id).all()


def obtener_usuario(db: Session, usuario_id: int) -> Usuario:
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )
    return usuario


def actualizar_usuario(
    db: Session, usuario_id: int, datos: UsuarioActualizar, actor_id: int
) -> tuple[Usuario, list[str]]:
    """Devuelve (usuario, lista de cambios aplicados) para la auditoría."""
    usuario = obtener_usuario(db, usuario_id)

    if usuario.rol == RolUsuario.administrador:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No se puede modificar a un administrador",
        )

    cambios = datos.model_dump(exclude_unset=True)

    if usuario.id == actor_id and ("rol" in cambios or "activo" in cambios):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes cambiar tu propio rol ni desactivarte",
        )

    aplicados: list[str] = []
    for campo, valor in cambios.items():
        if valor is None and campo in ("rol", "activo"):
            continue
        if campo == "rol":
            nuevo = RolUsuario(valor.value if hasattr(valor, "value") else valor)
            if usuario.rol != nuevo:
                aplicados.append(f"rol: {usuario.rol.value} -> {nuevo.value}")
                usuario.rol = nuevo
        elif campo == "activo":
            if usuario.activo != valor:
                aplicados.append(f"activo: {usuario.activo} -> {valor}")
                usuario.activo = valor
        else:
            if getattr(usuario, campo) != valor:
                aplicados.append(f"{campo} actualizado")
                setattr(usuario, campo, valor)

    db.commit()
    db.refresh(usuario)
    return usuario, aplicados
