from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.auth import LoginRequest, RegisterUserRequest, TokenResponse
from app.services.auth_service import authenticate_user, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
async def create_user(payload: RegisterUserRequest, db: AsyncSession = Depends(get_db)):
    try:
        user = await register_user(db, payload)
        return {
            "id": str(user.id),
            "username": user.username,
            "full_name": user.full_name,
            "email": user.email,
        }
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Usuário ou e-mail já cadastrado") from exc


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    token = await authenticate_user(db, payload.username, payload.password)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")
    return TokenResponse(access_token=token)
