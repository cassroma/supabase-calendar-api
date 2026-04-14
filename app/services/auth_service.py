from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, get_password_hash, normalize_role, verify_password
from app.models.professional import Professional
from app.models.user import User
from app.schemas.auth import RegisterUserRequest


async def register_user(db: AsyncSession, payload: RegisterUserRequest) -> User:
    user = User(
        username=payload.username,
        full_name=payload.full_name,
        email=payload.email,
        role=normalize_role(payload.role),
        password_hash=get_password_hash(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, username: str, password: str) -> tuple[str, User] | None:
    result = await db.execute(select(User).where(User.username == username, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        return None
    return create_access_token(user.id, user.role), user


async def users_count(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(User))
    return int(result.scalar() or 0)


async def get_me_payload(db: AsyncSession, user: User) -> dict:
    professional_result = await db.execute(
        select(Professional)
        .where(
            Professional.user_id == user.id,
            Professional.is_active.is_(True)
        )
        .order_by(Professional.display_name.asc())
        .limit(1)
    )
    professional = professional_result.scalar_one_or_none()

    return {
        "id": str(user.id),
        "username": user.username,
        "full_name": user.full_name or user.username,
        "email": user.email,
        "role": (user.role or "professional"),
        "is_active": bool(user.is_active),
        "professional_id": str(professional.id) if professional else None,
        "professional_display_name": professional.display_name if professional else None,
    }


async def username_or_email_exists(db: AsyncSession, username: str, email: str | None, exclude_user_id=None) -> bool:
    filters = [User.username == username]
    if email:
        filters.append(User.email == email)

    stmt = select(User).where(or_(*filters))
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)

    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None
