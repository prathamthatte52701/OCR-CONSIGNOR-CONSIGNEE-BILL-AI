"""Step C: an email over 254 characters is refused on every entry point; exactly 254 passes the
shared validator; login answers an over-long address exactly like a wrong password."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.validators import is_valid_email
from app.main import app
from testkit import make_user

STRONG = "Zr8!kQ2mXv"
DOMAIN = "@example.io"
OK_254 = "a" * (254 - len(DOMAIN)) + DOMAIN
TOO_LONG = "a" * (255 - len(DOMAIN)) + DOMAIN


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_shared_validator_cap_is_254() -> None:
    assert len(OK_254) == 254 and is_valid_email(OK_254)
    assert len(TOO_LONG) == 255 and not is_valid_email(TOO_LONG)
    assert not is_valid_email("a" * 5000 + DOMAIN)


async def test_login_overlong_looks_like_a_wrong_password(client: TestClient) -> None:
    user = await make_user()
    wrong = client.post("/api/auth/login", json={"email": user["email"], "password": "nope"})
    for email in (TOO_LONG, "a" * 900 + DOMAIN):
        r = client.post("/api/auth/login", json={"email": email, "password": STRONG})
        assert r.status_code == 401
        assert r.json() == wrong.json() == {"detail": "Invalid email or password."}


async def test_login_exactly_254_is_an_ordinary_failed_login(client: TestClient) -> None:
    r = client.post("/api/auth/login", json={"email": OK_254, "password": STRONG})
    assert r.status_code == 401 and r.json() == {"detail": "Invalid email or password."}


async def test_signup_254_works_255_is_refused(client: TestClient) -> None:
    ok = client.post(
        "/api/auth/signup", json={"username": "abc", "email": OK_254, "password": STRONG}
    )
    assert ok.status_code == 201, ok.text
    bad = client.post(
        "/api/auth/signup", json={"username": "abd", "email": TOO_LONG, "password": STRONG}
    )
    assert bad.status_code in (400, 422)


async def test_reset_request_overlong_is_refused_not_a_500(client: TestClient) -> None:
    r = client.post("/api/auth/password-reset-request", json={"email": TOO_LONG})
    assert r.status_code in (400, 422)


async def test_profile_overlong_email_is_refused(client: TestClient) -> None:
    user = await make_user()
    r = client.patch("/api/auth/me", json={"email": TOO_LONG}, headers=user["headers"])
    assert r.status_code in (400, 422)


async def test_admin_change_email_overlong_is_refused(client: TestClient) -> None:
    admin, user = await make_user(role="admin"), await make_user()
    r = client.put(
        f"/api/admin/users/{user['id']}/email", json={"email": TOO_LONG}, headers=admin["headers"]
    )
    assert r.status_code in (400, 422)
    ok = client.put(
        f"/api/admin/users/{user['id']}/email", json={"email": OK_254}, headers=admin["headers"]
    )
    assert ok.status_code == 200, ok.text
