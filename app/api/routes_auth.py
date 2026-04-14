from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.schemas.auth import LoginRequest, RegisterUserRequest, TokenResponse, UserMeResponse
from app.services.auth_service import authenticate_user, get_me_payload, register_user, users_count

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
async def create_user(
    payload: RegisterUserRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles("master", "admin")),
):
    try:
        user = await register_user(db, payload)
        return {
            "id": str(user.id),
            "username": user.username,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role,
        }
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Usuário ou e-mail já cadastrado") from exc


@router.post("/bootstrap-register")
async def bootstrap_register(payload: RegisterUserRequest, db: AsyncSession = Depends(get_db)):
    total_users = await users_count(db)
    if total_users > 0:
        raise HTTPException(status_code=403, detail="Bootstrap disponível apenas sem usuários cadastrados")

    payload.role = "master"
    try:
        user = await register_user(db, payload)
        return {
            "id": str(user.id),
            "username": user.username,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role,
        }
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Usuário ou e-mail já cadastrado") from exc


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    auth_result = await authenticate_user(db, payload.username, payload.password)
    if not auth_result:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")
    token, user = auth_result
    return TokenResponse(
        access_token=token,
        role=user.role,
        user_id=str(user.id),
        full_name=user.full_name,
    )


@router.get("/me", response_model=UserMeResponse)
async def get_me(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await get_me_payload(db, current_user)
