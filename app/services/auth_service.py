from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.user import User
from app.schemas.auth import RegisterUserRequest


async def register_user(db: AsyncSession, payload: RegisterUserRequest) -> User:
    user = User(
        username=payload.username,
        full_name=payload.full_name,
        email=payload.email,
        password_hash=get_password_hash(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, username: str, password: str) -> str | None:
    result = await db.execute(select(User).where(User.username == username, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        return None
    return create_access_token(user.id)
