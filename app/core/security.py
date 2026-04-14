from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


ALLOWED_ROLES = {"master", "admin", "professional", "attendant"}


def normalize_role(role: str | None) -> str:
    normalized = (role or "professional").strip().lower()
    if normalized not in ALLOWED_ROLES:
        raise ValueError(f"Perfil inválido. Use um destes valores: {', '.join(sorted(ALLOWED_ROLES))}")
    return normalized


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)



def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)



def create_access_token(subject: str | Any, role: str, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    to_encode = {"exp": expire, "sub": str(subject), "role": normalize_role(role)}
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)



def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Token inválido ou expirado") from exc
