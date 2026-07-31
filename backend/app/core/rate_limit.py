"""Per-IP rate limiting (slowapi) plus a per-email limiter for login (needs async body read,
which slowapi's key func can't do since it must stay sync)."""

from limits import RateLimitItemPerMinute
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

_email_storage = MemoryStorage()
_email_limiter = MovingWindowRateLimiter(_email_storage)
_LOGIN_EMAIL_LIMIT = RateLimitItemPerMinute(20, 15)  # 20 requests per 15 minutes


def check_login_email_limit(email: str) -> bool:
    """Returns True if this email is still within its login-attempt budget."""
    return _email_limiter.hit(_LOGIN_EMAIL_LIMIT, "login-email", email)
