from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User

security = HTTPBearer(auto_error=False)


async def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key inválida")


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
