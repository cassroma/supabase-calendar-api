from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: str
    full_name: str


class RegisterUserRequest(BaseModel):
    username: str
    full_name: str
    email: EmailStr | None = None
    password: str = Field(min_length=6)
    role: str = "professional"


class UserMeResponse(BaseModel):
    id: str
    username: str
    full_name: str
    email: EmailStr | None = None
    role: str
    is_active: bool
    professional_id: str | None = None
    professional_display_name: str | None = None
