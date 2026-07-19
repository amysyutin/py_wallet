from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.db.models.user import UserRole


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr | None
    role: UserRole
    created_at: datetime


class TelegramAuthRequest(BaseModel):
    init_data: str = Field(min_length=1, max_length=16384)


class TelegramAuthResponse(Token):
    is_new_user: bool
    email_linked: bool


class TelegramLinkEmailRequest(UserLogin):
    pass
