"""Request/response schemas for auth routes."""

from app.core.base_model import CamelModel


class SignupRequest(CamelModel):
    username: str
    email: str
    password: str


class LoginRequest(CamelModel):
    email: str
    password: str


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
    username: str | None = None
    email: str | None = None


class ChangePasswordRequest(CamelModel):
    current_password: str
    new_password: str


class ForgotPasswordVerifyRequest(CamelModel):
    username: str
    email: str


class ForgotPasswordResetRequest(CamelModel):
    username: str
    email: str
    new_password: str
