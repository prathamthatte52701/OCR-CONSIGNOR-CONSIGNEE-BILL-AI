"""Auth-input rules: username 3-8 chars; password 8-64 BYTES (so bcrypt's 72-byte limit can never
silently cut a password), upper+lower+digit+special, no whitespace/control characters, not a
well-known weak password, and not built from the user's own username / email."""

import re

from app.core.common_passwords import COMMON_BASE_WORDS

USERNAME_RE = re.compile(r"^.{3,8}$")
# Character-class rule only - length is enforced separately, in bytes (see password_problem).
PASSWORD_CLASSES_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9\s]).+$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

# Digits and punctuation people tack onto the end of a common word ("Password1!", "qwerty@2024").
_TRAILING_STRIP_CHARS = "0123456789" + r"""!@#$%^&*()-_=+[]{};:'",.<>/?\|`~"""

MIN_PASSWORD_BYTES = 8
MAX_PASSWORD_BYTES = 64
# A username / email local part shorter than this is too generic to ban as a substring
# (it would reject half of all passwords), so the "contains your name" rule skips it.
MIN_PERSONAL_PART_LENGTH = 3

PASSWORD_LENGTH_ERROR = (
    "Password must be 8-64 characters long (letters with accents or non-English characters "
    "count as more than one)."
)
PASSWORD_RULE_ERROR = (
    "Password needs an upper-case letter, a lower-case letter, a number and a special "
    "character, with no spaces."
)
PASSWORD_COMMON_ERROR = "That password is too common. Please choose a stronger one."
PASSWORD_PERSONAL_ERROR = "Password must not contain your username or the start of your email."


def is_valid_username(username: str) -> bool:
    return bool(USERNAME_RE.match(username)) and not username.isspace()


def _has_forbidden_chars(password: str) -> bool:
    # Whitespace, control characters (NUL would make bcrypt raise) are never allowed.
    return any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in password)


def password_byte_length(password: str) -> int | None:
    """UTF-8 length, or None for text that cannot be encoded at all (a lone surrogate)."""
    try:
        return len(password.encode("utf-8"))
    except UnicodeEncodeError:
        return None


def is_valid_password(password: str) -> bool:
    """Format rules only (length in bytes, character classes) - no blocklist / personal check."""
    size = password_byte_length(password)
    if size is None or not MIN_PASSWORD_BYTES <= size <= MAX_PASSWORD_BYTES:
        return False
    if _has_forbidden_chars(password):
        return False
    return bool(PASSWORD_CLASSES_RE.match(password))


def is_common_password(password: str) -> bool:
    """True for a well-known weak password. Lowercases and strips trailing digits/symbols
    first, so "Password1!", "PASSWORD123#" and "pAssw0rd" are all caught by one blocklist
    entry. Only meant for NEW passwords (signup / change / reset) - never for login."""
    base = password.lower().rstrip(_TRAILING_STRIP_CHARS)
    return base in COMMON_BASE_WORDS


def contains_personal_info(password: str, username: str | None, email: str | None) -> bool:
    """True when the password embeds the username or the part of the email before the @."""
    lowered = password.lower()
    parts = [(username or "").strip().lower(), (email or "").strip().lower().split("@")[0]]
    return any(len(part) >= MIN_PERSONAL_PART_LENGTH and part in lowered for part in parts)


def password_problem(
    password: str, username: str | None = None, email: str | None = None
) -> str | None:
    """The first reason a NEW password is unacceptable (a user-facing message), else None.
    Used for signup, change-password and forgot-password reset - never for login."""
    size = password_byte_length(password)
    if size is None or not MIN_PASSWORD_BYTES <= size <= MAX_PASSWORD_BYTES:
        return PASSWORD_LENGTH_ERROR
    if _has_forbidden_chars(password) or not PASSWORD_CLASSES_RE.match(password):
        return PASSWORD_RULE_ERROR
    if is_common_password(password):
        return PASSWORD_COMMON_ERROR
    if contains_personal_info(password, username, email):
        return PASSWORD_PERSONAL_ERROR
    return None


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email))


def normalize_email(email: str) -> str:
    return email.strip().lower()
