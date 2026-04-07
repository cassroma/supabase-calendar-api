from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterUserRequest(BaseModel):
    username: str
    full_name: str
    email: EmailStr | None = None
    password: str
