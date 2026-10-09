"""Password hashing (bcrypt) and JWT sign/decode (PyJWT, HS256 only)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from jwt import PyJWTError

from app.core.config import settings

SALT_ROUNDS = 10
TOKEN_TTL = timedelta(days=7)
JWT_ALGORITHM = "HS256"  # the ONLY algorithm ever signed with or accepted


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(SALT_ROUNDS)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # bcrypt 5 raises for passwords over 72 bytes and for a malformed stored hash; either
        # way the answer for a login attempt is simply "no", never a 500.
        return False


# Verified against when the account does not exist (or has no password), so an unknown email
# costs exactly one bcrypt check - same as a wrong password - and response time cannot be used
# to tell the two apart. Same cost factor as real hashes (SALT_ROUNDS).
DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-constant-time-login")


def sign_token(user_id: str, token_version: int, role: str) -> str:
    payload = {
        "userId": user_id,
        "tokenVersion": token_version,
        "role": role,
        "exp": datetime.now(UTC) + TOKEN_TTL,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        # algorithms is pinned (never taken from the token's own header, so "alg: none" and
        # algorithm-confusion tokens are refused) and an expiry claim is mandatory.
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp"]},
        )
    except PyJWTError:
        return None
