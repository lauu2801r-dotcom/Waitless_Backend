from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.modules.auth.models import RolUsuario, Usuario
from app.modules.usuarios.schemas import EmpleadoCrear, UsuarioActualizar


def crear_empleado(db: Session, datos: EmpleadoCrear, restaurante_id: Optional[int]) -> Usuario:
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
        restaurante_id=restaurante_id,
        cargo=datos.cargo.value,
        verificado=True,
        activo=True,
    )
    db.add(empleado)
    db.commit()
    db.refresh(empleado)
    return empleado


def listar_usuarios(
    db: Session,
    restaurante_id: Optional[int],
    activo: Optional[bool] = None,
    buscar: Optional[str] = None,
):
    """Personal (empleados) del restaurante del administrador."""
    if restaurante_id is None:
        return []
    q = db.query(Usuario).filter(
        Usuario.rol == RolUsuario.empleado,
        Usuario.restaurante_id == restaurante_id,
    )
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


def obtener_usuario(db: Session, usuario_id: int, restaurante_id: Optional[int]) -> Usuario:
    usuario = db.query(Usuario).filter(
        Usuario.id == usuario_id,
        Usuario.rol == RolUsuario.empleado,
        Usuario.restaurante_id == restaurante_id,
    ).first()
    if not usuario or restaurante_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )
    return usuario


def actualizar_usuario(
    db: Session, usuario_id: int, datos: UsuarioActualizar, actor_id: int,
    restaurante_id: Optional[int],
) -> tuple[Usuario, list[str]]:
    """Devuelve (usuario, lista de cambios aplicados) para la auditoría."""
    usuario = obtener_usuario(db, usuario_id, restaurante_id)

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
                if nuevo != RolUsuario.empleado:
                    usuario.restaurante_id = None  # deja de ser personal del restaurante
        elif campo == "cargo":
            nuevo_cargo = valor.value if hasattr(valor, "value") else valor
            if valor is not None and usuario.cargo != nuevo_cargo:
                aplicados.append(f"cargo: {usuario.cargo} -> {nuevo_cargo}")
                usuario.cargo = nuevo_cargo
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
