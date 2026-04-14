from collections.abc import Callable
from typing import Any

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_token
from app.db.session import get_db
from app.models.professional import Professional
from app.models.user import User

security = HTTPBearer(auto_error=False)


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias=settings.api_key_header_name)
) -> None:
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key inválida")


async def require_manychat_integration_token(
    manychat_integration_token: str | None = Header(
        default=None,
        alias="X-Manychat-Integration-Token",
    )
) -> None:
    if manychat_integration_token != settings.manychat_integration_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ManyChat integration token inválido",
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token obrigatório")

    try:
        payload = decode_token(credentials.credentials)
        subject = payload.get("sub")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    result = await db.execute(select(User).where(User.id == subject, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado")
    return user


async def get_current_professional(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Professional | None:
    result = await db.execute(
        select(Professional).where(Professional.user_id == current_user.id, Professional.is_active.is_(True))
    )
    return result.scalar_one_or_none()



def require_roles(*allowed_roles: str) -> Callable[..., Any]:
    allowed = {role.strip().lower() for role in allowed_roles}

    async def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role.lower() not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuário sem permissão")
        return current_user

    return dependency


async def require_same_professional_or_admin(
    professional_id: str,
    current_user: User = Depends(get_current_user),
    current_professional: Professional | None = Depends(get_current_professional),
) -> User:
    if current_user.role.lower() in {"master", "admin"}:
        return current_user

    if current_user.role.lower() == "professional" and current_professional and str(current_professional.id) == str(professional_id):
        return current_user

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuário sem permissão para este profissional")
