"""Config values as consignor really treats them. Settings come from explicit values only
(`_env_file=None`); the real backend/.env is never read and no database is contacted.

A blank or whitespace-only MONGO_DB_NAME / FRONTEND_ORIGIN / ADMIN_ORIGIN means "use the
default"; string values are whitespace-stripped; a blank MONGO_URI fails at startup."""

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings

URI = "mongodb://localhost:27017/placeholder"
SECRET = "x" * 48
ENV_KEYS = ("MONGO_URI", "MONGO_DB_NAME", "JWT_SECRET", "GROQ_API_KEYS", "FRONTEND_ORIGIN",
            "ADMIN_ORIGIN", "CHAT_FILES_MAX_TOTAL_MB")  # fmt: skip


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _settings(**values: Any) -> Settings:
    base: dict[str, Any] = {"MONGO_URI": URI, "JWT_SECRET": SECRET, "GROQ_API_KEYS": "k1"}
    base.update(values)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


def test_missing_optional_values_use_the_defaults() -> None:
    s = _settings()
    assert s.mongo_db_name == "docintel_cons_cons"
    assert s.frontend_origin == "http://localhost:6001"
    assert s.admin_origin == "http://localhost:7000"
    assert s.port == 9000


@pytest.mark.parametrize("blank", ["", "   ", "\t", " \n "])
def test_blank_db_name_and_origins_use_the_defaults(blank: str) -> None:
    s = _settings(MONGO_DB_NAME=blank, FRONTEND_ORIGIN=blank, ADMIN_ORIGIN=blank)
    assert s.mongo_db_name == "docintel_cons_cons"
    assert s.cors_origins == ["http://localhost:6001", "http://localhost:7000"]


def test_values_are_whitespace_stripped() -> None:
    s = _settings(
        MONGO_DB_NAME="  my_db  ",
        FRONTEND_ORIGIN=" http://localhost:3000 ",
        ADMIN_ORIGIN="\thttp://localhost:3001\n",
        MONGO_URI="  " + URI + " ",
    )
    assert s.mongo_db_name == "my_db"
    assert s.cors_origins == ["http://localhost:3000", "http://localhost:3001"]
    assert s.mongo_uri == URI


def test_trailing_slash_on_an_origin_is_left_alone() -> None:
    assert _settings(FRONTEND_ORIGIN="http://localhost:3000/").frontend_origin.endswith("3000/")


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_blank_mongo_uri_fails_with_a_clear_message(blank: str) -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(MONGO_URI=blank)
    assert "MONGO_URI" in str(exc.value)


def test_real_values_are_kept() -> None:
    s = _settings(MONGO_DB_NAME="my_db", FRONTEND_ORIGIN="http://localhost:3000")
    assert s.mongo_db_name == "my_db"
    assert s.cors_origins[0] == "http://localhost:3000"


def test_missing_required_values_fail() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, JWT_SECRET=SECRET, GROQ_API_KEYS="k")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Settings(_env_file=None, MONGO_URI=URI, GROQ_API_KEYS="k")  # type: ignore[call-arg]


@pytest.mark.parametrize("secret", ["", "short"])
def test_blank_or_short_jwt_secret_fails(secret: str) -> None:
    with pytest.raises(ValidationError):
        _settings(JWT_SECRET=secret)


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_blank_chat_cap_means_75(blank: str) -> None:
    assert _settings(CHAT_FILES_MAX_TOTAL_MB=blank).chat_files_max_total_mb == 75
    assert _settings().chat_files_max_total_mb == 75


@pytest.mark.parametrize("raw,expected", [("1", 1), (" 200 ", 200), (100000, 100000)])
def test_chat_cap_valid_values(raw: object, expected: int) -> None:
    assert _settings(CHAT_FILES_MAX_TOTAL_MB=raw).chat_files_max_total_mb == expected


@pytest.mark.parametrize("bad", ["0", "-1", "100001", "1.5", "abc", "1e3", "٣"])
def test_chat_cap_invalid_values_are_rejected(bad: str) -> None:
    with pytest.raises(ValidationError):
        _settings(CHAT_FILES_MAX_TOTAL_MB=bad)


def test_groq_keys_split_and_skip_blanks() -> None:
    assert _settings(GROQ_API_KEYS=" a , ,b,").groq_api_keys == ["a", "b"]


def test_env_example_loads_with_the_required_values_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Load a copy-equivalent of the shipped template (required values come from the process
    environment). The real backend/.env is never opened."""
    template = Path(__file__).resolve().parents[2] / ".env.example"
    assert template.exists()
    monkeypatch.setenv("MONGO_URI", URI)
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.setenv("GROQ_API_KEYS", "k1")
    s = Settings(_env_file=template)  # type: ignore[call-arg]
    assert s.jwt_secret == SECRET  # process env wins over the template line
