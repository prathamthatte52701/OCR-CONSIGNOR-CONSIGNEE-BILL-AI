"""T2: unknown email, wrong password, password-less account and over-long password must be
indistinguishable (same status, same body, one bcrypt check each) and never a 500."""

import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.core import security
from app.core.security import DUMMY_PASSWORD_HASH, hash_password
from app.features.auth import router as auth_router
from app.main import app
from testkit import current_db

PASSWORD = "Str0ng!Passw0rd"  # noqa: S105 - test-only value
GENERIC = "Invalid email or password."


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


async def _user(*, with_hash: bool = True) -> dict[str, Any]:
    uid = ObjectId()
    doc: dict[str, Any] = {
        "_id": uid,
        "username": "timing",
        "email": f"timing-{uid}@example.invalid",
        "role": "user",
        "status": "approved",
        "tokenVersion": 0,
        "createdAt": datetime.now(UTC),
        "updatedAt": datetime.now(UTC),
    }
    if with_hash:
        doc["passwordHash"] = hash_password(PASSWORD)
    await current_db().users.insert_one(doc)
    return doc


def _login(client: TestClient, email: str, password: str) -> Any:
    return client.post("/api/auth/login", json={"email": email, "password": password})


async def test_unknown_email_and_wrong_password_have_identical_responses(
    client: TestClient,
) -> None:
    user = await _user()
    unknown = _login(client, "nobody-here@example.invalid", "Wr0ng!Passw0rd")
    wrong = _login(client, user["email"], "Wr0ng!Passw0rd")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json() == {"detail": GENERIC}


async def test_every_failure_path_runs_exactly_one_bcrypt_check(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_user = await _user()
    no_password = await _user(with_hash=False)
    calls: list[str] = []
    original = security.verify_password

    def spy(password: str, password_hash: str) -> bool:
        calls.append(password_hash)
        return original(password, password_hash)

    monkeypatch.setattr(auth_router, "verify_password", spy)

    _login(client, "nobody-here@example.invalid", "Wr0ng!Passw0rd")
    assert calls == [DUMMY_PASSWORD_HASH]  # unknown email -> dummy hash
    calls.clear()
    _login(client, no_password["email"], "Wr0ng!Passw0rd")
    assert calls == [DUMMY_PASSWORD_HASH]  # no password -> dummy hash
    calls.clear()
    _login(client, real_user["email"], "Wr0ng!Passw0rd")
    assert calls == [real_user["passwordHash"]]  # wrong password -> real hash, still one check


async def test_account_without_password_hash_is_401_not_500(client: TestClient) -> None:
    user = await _user(with_hash=False)
    r = _login(client, user["email"], PASSWORD)
    assert r.status_code == 401 and r.json() == {"detail": GENERIC}


@pytest.mark.parametrize("password", ["x" * 73, "x" * 500, "é" * 40, "pass\x00word"])
async def test_overlong_or_odd_password_is_401_not_500(client: TestClient, password: str) -> None:
    user = await _user()
    r = _login(client, user["email"], password)
    assert r.status_code in (400, 401, 422)
    assert r.status_code != 500


async def test_correct_password_still_logs_in(client: TestClient) -> None:
    user = await _user()
    r = _login(client, user["email"], PASSWORD)
    assert r.status_code == 200 and r.json()["token"]


async def test_unknown_email_is_not_the_fast_path(client: TestClient) -> None:
    user = await _user()

    def timed(email: str) -> float:
        start = time.perf_counter()
        assert _login(client, email, "Wr0ng!Passw0rd").status_code == 401
        return time.perf_counter() - start

    unknown = min(timed(f"nobody{i}@example.invalid") for i in range(3))
    wrong = min(timed(user["email"]) for _ in range(3))
    # Without the dummy hash an unknown email returns in ~1 ms vs ~60 ms for a real bcrypt.
    assert unknown > wrong * 0.5, (unknown, wrong)


def test_verify_password_never_raises_on_bad_input() -> None:
    assert security.verify_password("x" * 100, DUMMY_PASSWORD_HASH) is False
    assert security.verify_password("anything", "not-a-bcrypt-hash") is False
    assert security.verify_password("", DUMMY_PASSWORD_HASH) is False
