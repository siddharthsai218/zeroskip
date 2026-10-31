import re
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict

Role = Literal["ADMIN", "STAFF", "CUSTOMER"]

_EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(value: str) -> str:
    value = value.strip().lower()
    if not _EMAIL_REGEX.match(value):
        raise ValueError("Invalid email address")
    return value


class UserRegister(BaseModel):
    email: str
    password: str
    full_name: str = Field(..., min_length=1, max_length=120)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)


class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str = Field(..., min_length=1, max_length=120)
    role: Role = "CUSTOMER"

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)


class UserLogin(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: Role
    is_active: bool
    created_at: str


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=120)
    password: Optional[str] = None


class UserStatusUpdate(BaseModel):
    is_active: bool


class PasswordResetRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)


class PasswordResetConfirm(BaseModel):
    token: str = Field(..., min_length=1)
    new_password: str


class MessageResponse(BaseModel):
    message: str
