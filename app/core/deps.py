"""
Dependencias compartidas de seguridad (autenticación + control de acceso por rol).

Uso en un router:
    from app.core.deps import get_current_user, solo_admin, admin_o_empleado

    @router.get("/algo")
    def algo(current_user: dict = Depends(solo_admin)):
        ...
"""
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import verify_token
from app.modules.auth.models import RolUsuario, Usuario

# auto_error=False para responder nosotros el 401 con nuestro mensaje.
# Además hace que Swagger (/docs) muestre el botón "Authorize".
bearer_scheme = HTTPBearer(auto_error=False)


def _no_autorizado(detalle: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detalle,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> dict:
    """
    Valida el JWT y confirma contra la BD que el usuario sigue existiendo,
    verificado y activo. El rol se toma de la BD (no del token), así un
    cambio de rol aplica de inmediato sin cerrar sesión (RF-012).

    Retorna: {"sub": "<id>", "email": "...", "rol": "cliente|empleado|administrador"}
    """
    if credentials is None:
        raise _no_autorizado("Token requerido")

    payload = verify_token(credentials.credentials)
    if not payload or "sub" not in payload:
        raise _no_autorizado("Token inválido o expirado")

    try:
        usuario_id = int(payload["sub"])
    except (TypeError, ValueError):
        raise _no_autorizado("Token inválido")

    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario or not usuario.activo or not usuario.verificado:
        raise _no_autorizado("Sesión inválida")

    return {
        "sub": str(usuario.id),
        "email": usuario.email,
        "rol": usuario.rol.value,
    }


def require_roles(*roles: RolUsuario):
    """Fábrica de dependencias: solo deja pasar a los roles indicados (si no, 403)."""
    permitidos = {r.value for r in roles}

    def dependency(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user["rol"] not in permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para realizar esta acción",
            )
        return current_user

    return dependency


# Atajos listos para usar
solo_admin = require_roles(RolUsuario.administrador)
admin_o_empleado = require_roles(RolUsuario.administrador, RolUsuario.empleado)


def es_personal(current_user: dict) -> bool:
    """True si el usuario es empleado o administrador."""
    return current_user["rol"] in (
        RolUsuario.administrador.value,
        RolUsuario.empleado.value,
    )
