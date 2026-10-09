"""Request/response schemas for auth routes."""

from typing import Any

from pydantic import Field

from app.core.base_model import CamelModel

# Hard upper bounds on every auth input. Deliberately looser than the business rules (username
# 3-8, password 8-64 bytes, ...) which stay in core/validators.py and give friendly 400 messages;
# these only stop absurdly large values from being parsed, hashed or stored.
MAX_USERNAME_FIELD = 32
MAX_EMAIL_FIELD = 254  # RFC 5321 limit for an address
MAX_PASSWORD_FIELD = 128


class SignupRequest(CamelModel):
    username: str = Field(max_length=MAX_USERNAME_FIELD)
    email: str = Field(max_length=MAX_EMAIL_FIELD)
    password: str = Field(max_length=MAX_PASSWORD_FIELD)


class LoginRequest(CamelModel):
    email: str = Field(max_length=MAX_EMAIL_FIELD)
    password: str = Field(max_length=MAX_PASSWORD_FIELD)


class AuthResponse(CamelModel):
    token: str
    username: str
    email: str
    role: str


class MeResponse(CamelModel):
    id: str
    username: str
    email: str
    role: str


class UpdateMeRequest(CamelModel):
    username: str | None = Field(default=None, max_length=MAX_USERNAME_FIELD)
    email: str | None = Field(default=None, max_length=MAX_EMAIL_FIELD)


class ChangePasswordRequest(CamelModel):
    current_password: str = Field(max_length=MAX_PASSWORD_FIELD)
    new_password: str = Field(max_length=MAX_PASSWORD_FIELD)


class ForgotPasswordVerifyRequest(CamelModel):
    username: str = Field(max_length=MAX_USERNAME_FIELD)
    email: str = Field(max_length=MAX_EMAIL_FIELD)


class ForgotPasswordResetRequest(CamelModel):
    username: str = Field(max_length=MAX_USERNAME_FIELD)
    email: str = Field(max_length=MAX_EMAIL_FIELD)
    new_password: str = Field(max_length=MAX_PASSWORD_FIELD)


class ActivityListResponse(CamelModel):
    items: list[dict[str, Any]]
    total: int
    page: int
    limit: int
