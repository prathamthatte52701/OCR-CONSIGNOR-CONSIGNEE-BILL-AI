"""Safe defaults: no secret has a default, JWT secret length is enforced, docs and production
flags default safe, CORS is never a wildcard, no real identity or open bind in source.
Settings are built from explicit values only (`_env_file=None`); the real .env is never read."""

import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings

BACKEND = Path(__file__).resolve().parents[2]
URI = "mongodb://localhost:27017/placeholder"
SECRET = "x" * 48
KEYS = "k1"
ENV_KEYS = (
    "MONGO_URI", "GROQ_API_KEYS", "JWT_SECRET", "MONGO_DB_NAME", "NODE_ENV", "ENABLE_DOCS",
    "FRONTEND_ORIGIN", "ADMIN_ORIGIN", "ADMIN_1_PASSWORD", "ADMIN_2_PASSWORD", "ADMIN_1_EMAIL",
)  # fmt: skip


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _settings(**values: Any) -> Settings:
    base: dict[str, Any] = {"MONGO_URI": URI, "JWT_SECRET": SECRET, "GROQ_API_KEYS": KEYS}
    base.update(values)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


@pytest.mark.parametrize("missing", ["MONGO_URI", "JWT_SECRET", "GROQ_API_KEYS"])
def test_secrets_have_no_default(missing: str) -> None:
    values: dict[str, Any] = {"MONGO_URI": URI, "JWT_SECRET": SECRET, "GROQ_API_KEYS": KEYS}
    del values[missing]
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_admin_identities_and_passwords_default_to_empty() -> None:
    s = _settings()
    for field in ("admin_1_email", "admin_1_password", "admin_1_username",
                  "admin_2_email", "admin_2_password", "admin_2_username"):  # fmt: skip
        assert getattr(s, field) == "", field


@pytest.mark.parametrize("secret", ["", "short", "x" * 31])
def test_short_jwt_secret_is_refused(secret: str) -> None:
    with pytest.raises(ValidationError):
        _settings(JWT_SECRET=secret)


def test_32_char_jwt_secret_is_accepted() -> None:
    assert _settings(JWT_SECRET="x" * 32).jwt_secret == "x" * 32


def test_flags_default_safe() -> None:
    s = _settings()
    assert s.enable_docs is False
    assert s.environment == "development" and s.is_production is False


def test_default_origins_are_local_not_wildcard() -> None:
    s = _settings()
    assert s.cors_origins == ["http://localhost:6001", "http://localhost:7000"]
    assert all(o.startswith("http://localhost:") for o in s.cors_origins)
    assert "*" not in "".join(s.cors_origins)


def test_the_real_app_does_not_allow_a_wildcard_origin() -> None:
    from app.main import app

    cors = [m for m in app.user_middleware if getattr(m.cls, "__name__", "") == "CORSMiddleware"]
    assert len(cors) == 1
    origins: Any = cors[0].kwargs["allow_origins"]
    assert "*" not in origins


def test_production_flag_is_case_insensitive() -> None:
    assert _settings(NODE_ENV="Production").is_production is True


def _sources() -> list[Path]:
    return [p for p in (BACKEND / "app").rglob("*.py") if not p.name.startswith("test_")]


def test_no_real_admin_identity_hardcoded_in_source() -> None:
    pattern = re.compile(r"arjav99jain|prathamthatte527|Arjav Jain|Pratham Thatte")
    assert [p.name for p in _sources() if pattern.search(p.read_text(encoding="utf-8"))] == []


def test_seed_admin_takes_identities_from_settings_not_literals() -> None:
    text = (BACKEND / "app" / "scripts" / "seed_admin.py").read_text(encoding="utf-8")
    assert "settings.admin_1_email" in text or "admin_1_email" in text
    assert not re.search(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", text), "email literal in seed_admin.py"


def test_app_never_starts_a_server_bound_to_all_interfaces() -> None:
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        assert "0.0.0.0" not in text, path.name  # noqa: S104
        assert "uvicorn.run" not in text, path.name


def test_env_example_holds_no_secret_values() -> None:
    lines = (BACKEND / ".env.example").read_text(encoding="utf-8").splitlines()
    for line in lines:
        key, _, value = line.partition("=")
        if key.strip() in {"JWT_SECRET", "ADMIN_1_PASSWORD", "ADMIN_2_PASSWORD", "GROQ_API_KEYS"}:
            assert len(value.strip().strip('"')) < 20 and "gsk_" not in value, key
