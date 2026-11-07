"""Per-IP rate limiting (slowapi) plus a per-email limiter for login (needs async body read,
which slowapi's key func can't do since it must stay sync)."""

from fastapi import Request
from limits import RateLimitItemPerHour, RateLimitItemPerMinute
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.security import decode_token

limiter = Limiter(key_func=get_remote_address)

# Uploads per IP (shared office IP, so well above one person's use; only blocks scripted spam).
UPLOAD_LIMIT = "120/hour"
# Bulk uploads (up to 5 sets each), a separate budget from single uploads.
BULK_UPLOAD_LIMIT = "30/hour"


def user_or_ip_key(request: Request) -> str:
    """Per-account key: decodes the JWT off the Authorization header (a slowapi key_func must
    stay sync). Falls back to the IP for a missing/invalid token; the route auth 401s it anyway."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and token:
        payload = decode_token(token.strip())
        if payload and payload.get("userId"):
            return f"user:{payload['userId']}"
    return get_remote_address(request)


_email_storage = MemoryStorage()
_email_limiter = MovingWindowRateLimiter(_email_storage)
_LOGIN_EMAIL_LIMIT = RateLimitItemPerMinute(20, 15)  # 20 requests per 15 minutes


# Password-reset REQUESTS per email: its own storage so spamming requests for someone's address
# can never eat that person's login attempts. The route applies it to EVERY email it is sent
# (existing or not), so a 429 reveals nothing about whether an account exists.
_reset_limiter = MovingWindowRateLimiter(MemoryStorage())
_RESET_EMAIL_LIMIT = RateLimitItemPerHour(3)


def check_reset_email_limit(email: str) -> bool:
    """Returns True if this email is still within its reset-request budget."""
    return _reset_limiter.hit(_RESET_EMAIL_LIMIT, "pwreset", email.strip().lower())


def check_login_email_limit(email: str) -> bool:
    """Returns True if this email is still within its login-attempt budget."""
    return _email_limiter.hit(_LOGIN_EMAIL_LIMIT, "login-email", email)
