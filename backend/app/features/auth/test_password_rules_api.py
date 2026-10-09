"""T9 (API): the password rules apply to signup, change-password and forgot-password reset - and
ONLY to those (an existing weak password must still be able to log in)."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.core.validators import (
    PASSWORD_COMMON_ERROR,
    PASSWORD_LENGTH_ERROR,
    PASSWORD_PERSONAL_ERROR,
    PASSWORD_RULE_ERROR,
)
from app.main import app
from testkit import PASSWORD, current_db, make_user

STRONG = "Zr8!kQ2mXv"


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _signup(client: TestClient, username: str, email: str, password: str) -> Any:
    return client.post(
        "/api/auth/signup", json={"username": username, "email": email, "password": password}
    )


BAD_NEW_PASSWORDS = [
    ("Ab1!xyz", PASSWORD_LENGTH_ERROR),  # 7 bytes
    ("Ab1!" + "x" * 61, PASSWORD_LENGTH_ERROR),  # 65 bytes
    ("Ab1!" + "é" * 31, PASSWORD_LENGTH_ERROR),  # 66 bytes, only 35 characters
    ("abcdefg1!", PASSWORD_RULE_ERROR),  # no upper
    ("Abcdefgh!", PASSWORD_RULE_ERROR),  # no digit
    ("Abc def1!", PASSWORD_RULE_ERROR),  # whitespace
    ("Abcdef1!\x00", PASSWORD_RULE_ERROR),  # NUL (would crash bcrypt if it got through)
    ("Welcome@1", PASSWORD_COMMON_ERROR),
    ("Qwerty123!", PASSWORD_COMMON_ERROR),
    ("Xk#mynameZ9", PASSWORD_PERSONAL_ERROR),  # contains the username "myname"
    ("Xk#jane.roe9Z", PASSWORD_PERSONAL_ERROR),  # contains the email local part "jane.roe"
]


@pytest.mark.parametrize(("password", "message"), BAD_NEW_PASSWORDS)
async def test_signup_rejects_bad_passwords_and_creates_no_user(
    client: TestClient, password: str, message: str
) -> None:
    email = f"pw-{ObjectId()}@example.invalid"
    # username/local part chosen so the "personal info" cases are real
    r = _signup(client, "myname", email.replace(email.split("@")[0], "jane.roe"), password)
    assert r.status_code == 400 and r.json()["detail"] == message
    assert await current_db().users.count_documents({"username": "myname"}) == 0


async def test_signup_accepts_a_strong_password(client: TestClient) -> None:
    r = _signup(client, "goodpw", f"pw-{ObjectId()}@example.invalid", STRONG)
    assert r.status_code == 201


async def test_signup_accepts_the_64_byte_maximum(client: TestClient) -> None:
    longest = "Zr8!" + "kQ2mXv" * 10  # 64 bytes
    assert len(longest.encode()) == 64
    email = f"pw-{ObjectId()}@example.invalid"
    assert _signup(client, "maxpw", email, longest).status_code == 201
    # Pending account: correct password gets the approval 403 (not a 500 / not a 401).
    login = client.post("/api/auth/login", json={"email": email, "password": longest})
    assert login.status_code == 403


@pytest.mark.parametrize(("password", "message"), BAD_NEW_PASSWORDS[:9])
async def test_change_password_enforces_the_same_rules(
    client: TestClient, password: str, message: str
) -> None:
    user = await make_user()
    r = client.post(
        "/api/auth/change-password",
        json={"currentPassword": PASSWORD, "newPassword": password},
        headers=user["headers"],
    )
    assert r.status_code == 400 and r.json()["detail"] == message
    # unchanged: the old password still logs in, tokenVersion not bumped
    assert (
        client.post(
            "/api/auth/login", json={"email": user["email"], "password": PASSWORD}
        ).status_code
        == 200
    )
    stored = await current_db().users.find_one({"_id": user["_id"]})
    assert stored is not None and stored["tokenVersion"] == 0


async def test_change_password_rejects_the_users_own_username_and_email(client: TestClient) -> None:
    user = await make_user(username="bobby")
    local = user["email"].split("@")[0]  # e.g. kit-<objectid>
    for bad in ("Xk#BobbyZ9a", f"Zq#{local}9X"):
        r = client.post(
            "/api/auth/change-password",
            json={"currentPassword": PASSWORD, "newPassword": bad},
            headers=user["headers"],
        )
        assert r.status_code == 400 and r.json()["detail"] == PASSWORD_PERSONAL_ERROR


async def test_change_password_success_rotates_the_session(client: TestClient) -> None:
    user = await make_user()
    r = client.post(
        "/api/auth/change-password",
        json={"currentPassword": PASSWORD, "newPassword": STRONG},
        headers=user["headers"],
    )
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=user["headers"]).status_code == 401  # old token dead
    assert (
        client.post(
            "/api/auth/login", json={"email": user["email"], "password": STRONG}
        ).status_code
        == 200
    )


@pytest.mark.parametrize(("password", "message"), BAD_NEW_PASSWORDS[:9])
async def test_forgot_password_reset_enforces_the_same_rules(
    client: TestClient, password: str, message: str
) -> None:
    user = await make_user(username="resetme")
    r = client.post(
        "/api/auth/forgot-password/reset",
        json={"username": "resetme", "email": user["email"], "newPassword": password},
    )
    assert r.status_code == 400 and r.json()["detail"] == message
    assert (
        client.post(
            "/api/auth/login", json={"email": user["email"], "password": PASSWORD}
        ).status_code
        == 200
    )


async def test_forgot_password_reset_rejects_password_built_from_the_username(
    client: TestClient,
) -> None:
    user = await make_user(username="resetme")
    r = client.post(
        "/api/auth/forgot-password/reset",
        json={"username": "resetme", "email": user["email"], "newPassword": "Xk#ResetMe9Z"},
    )
    assert r.status_code == 400 and r.json()["detail"] == PASSWORD_PERSONAL_ERROR


async def test_forgot_password_reset_success_and_no_account_oracle(client: TestClient) -> None:
    user = await make_user(username="resetme")
    ok = client.post(
        "/api/auth/forgot-password/reset",
        json={"username": "resetme", "email": user["email"], "newPassword": STRONG},
    )
    assert ok.status_code == 200
    assert (
        client.post(
            "/api/auth/login", json={"email": user["email"], "password": STRONG}
        ).status_code
        == 200
    )
    # A bad password is rejected with the SAME message whether or not the account exists
    real = client.post(
        "/api/auth/forgot-password/reset",
        json={"username": "resetme", "email": user["email"], "newPassword": "Welcome@1"},
    )
    ghost = client.post(
        "/api/auth/forgot-password/reset",
        json={"username": "ghost", "email": "ghost@example.invalid", "newPassword": "Welcome@1"},
    )
    assert real.status_code == ghost.status_code == 400
    assert real.json() == ghost.json() == {"detail": PASSWORD_COMMON_ERROR}


@pytest.mark.parametrize(
    "legacy_password", ["Password1!", "Welcome@1", "Abcdef1!", "Ab1!" + "x" * 36]
)
async def test_existing_weak_or_long_passwords_can_still_log_in(
    client: TestClient, legacy_password: str
) -> None:
    """The new rules are for NEW passwords only - never locking out an existing account."""
    uid = ObjectId()
    email = f"legacy-{uid}@example.invalid"
    await current_db().users.insert_one(
        {
            "_id": uid,
            "username": "legacy",
            "email": email,
            "passwordHash": hash_password(legacy_password),
            "role": "user",
            "status": "approved",
            "tokenVersion": 0,
            "createdAt": datetime.now(UTC),
            "updatedAt": datetime.now(UTC),
        }
    )
    r = client.post("/api/auth/login", json={"email": email, "password": legacy_password})
    assert r.status_code == 200 and r.json()["token"]
