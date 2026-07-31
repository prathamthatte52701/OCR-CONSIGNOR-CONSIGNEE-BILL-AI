"""Auth-input regexes — no whitespace allowed anywhere in password, username 3-8 chars."""

import re

USERNAME_RE = re.compile(r"^.{3,8}$")
PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9\s]).{8,32}$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def is_valid_username(username: str) -> bool:
    return bool(USERNAME_RE.match(username)) and not username.isspace()


def is_valid_password(password: str) -> bool:
    if any(ch.isspace() for ch in password):
        return False
    return bool(PASSWORD_RE.match(password))


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email))


def normalize_email(email: str) -> str:
    return email.strip().lower()
