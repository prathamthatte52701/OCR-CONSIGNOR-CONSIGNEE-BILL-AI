"""T11: the per-email login limiter (20 attempts / 15 minutes) - proven, not changed.
conftest.py resets the limiter storage before every test."""

import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core import rate_limit
from app.core.rate_limit import check_login_email_limit
from app.features.auth import router as auth_router
from app.main import app
from testkit import PASSWORD, make_user

TOO_MANY = "Too many login attempts. Try again later."


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _login(client: TestClient, email: str, password: str = "Wr0ng!Passw0rd") -> Any:
    return client.post("/api/auth/login", json={"email": email, "password": password})


async def test_the_21st_attempt_within_15_minutes_is_blocked(client: TestClient) -> None:
    user = await make_user()
    for attempt in range(1, 21):
        r = _login(client, user["email"])
        assert r.status_code == 401, f"attempt {attempt} should be a normal 401"
    blocked = _login(client, user["email"])
    assert blocked.status_code == 429 and blocked.json()["detail"] == TOO_MANY


async def test_a_different_email_is_not_affected(client: TestClient) -> None:
    victim, other = await make_user(), await make_user()
    for _ in range(21):
        _login(client, victim["email"])
    assert _login(client, victim["email"]).status_code == 429
    # another account (and a made-up address) still get ordinary answers
    assert _login(client, other["email"]).status_code == 401
    assert _login(client, other["email"], PASSWORD).status_code == 200
    assert _login(client, "never-seen@example.invalid").status_code == 401


async def test_the_correct_password_does_not_bypass_the_block(client: TestClient) -> None:
    user = await make_user()
    for _ in range(20):
        _login(client, user["email"])
    r = _login(client, user["email"], PASSWORD)  # right password, but the budget is spent
    assert r.status_code == 429 and "token" not in r.text


async def test_case_and_whitespace_variants_share_one_budget(client: TestClient) -> None:
    user = await make_user()
    variants = [user["email"], user["email"].upper(), f"  {user['email']}  ", user["email"].title()]
    for i in range(20):
        _login(client, variants[i % len(variants)])
    for variant in variants:
        assert _login(client, variant).status_code == 429


async def test_blocked_attempts_cost_no_bcrypt_work(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await make_user()
    for _ in range(20):
        _login(client, user["email"])
    calls: list[str] = []

    def spy(*_: Any, **__: Any) -> bool:
        calls.append("bcrypt")
        return False

    monkeypatch.setattr(auth_router, "verify_password", spy)
    assert _login(client, user["email"]).status_code == 429
    assert calls == []  # rejected before any password hashing - cheap for the server


async def test_blocked_unknown_email_looks_the_same_as_a_blocked_real_one(
    client: TestClient,
) -> None:
    real = await make_user()
    for email in (real["email"], "ghost@example.invalid"):
        for _ in range(20):
            _login(client, email)
    real_block = _login(client, real["email"])
    ghost_block = _login(client, "ghost@example.invalid")
    assert real_block.status_code == ghost_block.status_code == 429
    assert real_block.json() == ghost_block.json()  # the limiter is not an account-exists oracle


def test_the_budget_comes_back_after_the_window(monkeypatch: pytest.MonkeyPatch) -> None:
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    assert all(check_login_email_limit("window@example.invalid") for _ in range(20))
    assert check_login_email_limit("window@example.invalid") is False
    monkeypatch.setattr(time, "time", lambda: now + 14 * 60)  # still inside 15 minutes
    assert check_login_email_limit("window@example.invalid") is False
    monkeypatch.setattr(time, "time", lambda: now + 15 * 60 + 5)  # window slid past
    assert check_login_email_limit("window@example.invalid") is True


def test_exactly_20_attempts_pass_even_under_concurrency() -> None:
    results: list[bool] = []
    lock = threading.Lock()

    def attempt() -> None:
        ok = check_login_email_limit("race@example.invalid")
        with lock:
            results.append(ok)

    threads = [threading.Thread(target=attempt) for _ in range(60)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 60 and sum(results) == 20  # never 21, never 19


def test_the_limit_values_are_unchanged() -> None:
    """Guards against someone loosening the agreed 20 / 15 minutes by accident."""
    item = rate_limit._LOGIN_EMAIL_LIMIT
    assert item.amount == 20 and item.multiples == 15 and item.GRANULARITY.name == "minute"
