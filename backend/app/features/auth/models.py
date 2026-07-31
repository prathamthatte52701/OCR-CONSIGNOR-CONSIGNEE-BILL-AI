"""User document model."""

from typing import Literal

from app.core.base_model import MongoBaseModel


class User(MongoBaseModel):
    username: str
    email: str
    password_hash: str
    role: Literal["user", "admin"] = "user"
    token_version: int = 0
