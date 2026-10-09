"""T10: every auth request field has a maximum length, and the whole auth request body is capped,
so oversized input is refused cheaply (422 / 413) - never hashed, stored or turned into a 500."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from testkit import make_user

STRONG = "Zr8!kQ2mXv"
OK_EMAIL = "someone@example.invalid"


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# (method, path, base body) - every auth route that takes a body
AUTH_ROUTES: list[tuple[str, str, dict[str, Any]]] = [
    ("POST", "/api/auth/signup", {"username": "abc", "email": OK_EMAIL, "password": STRONG}),
    ("POST", "/api/auth/login", {"email": OK_EMAIL, "password": STRONG}),
    ("PATCH", "/api/auth/me", {"username": "abc"}),
    (
        "POST",
        "/api/auth/change-password",
        {"currentPassword": STRONG, "newPassword": "Zq!9wXe#2Lp"},
    ),
    ("POST", "/api/auth/forgot-password/verify", {"username": "abc", "email": OK_EMAIL}),
    (
        "POST",
        "/api/auth/forgot-password/reset",
        {"username": "abc", "email": OK_EMAIL, "newPassword": "Zq!9wXe#2Lp"},
    ),
]

# field -> first length that must be refused
FIELD_LIMITS = {
    "username": 33,
    "email": 255,
    "password": 129,
    "currentPassword": 129,
    "newPassword": 129,
}


def _oversized_cases() -> list[tuple[str, str, dict[str, Any], str]]:
    return [
        (method, path, body, field)
        for method, path, body in AUTH_ROUTES
        for field in FIELD_LIMITS
        if field in body
    ]


def _auth_headers(path: str, user: dict[str, Any]) -> dict[str, str]:
    return user["headers"] if path.endswith(("/me", "/change-password")) else {}


@pytest.mark.parametrize(("method", "path", "body", "field"), _oversized_cases())
async def test_field_over_its_maximum_is_422(
    client: TestClient, method: str, path: str, body: dict[str, Any], field: str
) -> None:
    user = await make_user()
    too_long = {**body, field: "x" * FIELD_LIMITS[field]}
    r = client.request(method, path, json=too_long, headers=_auth_headers(path, user))
    assert r.status_code == 422, (path, field, r.status_code)
    assert "at most" in r.text
    # the rejected value (possibly a password) is never echoed back, nor pydantic's raw input
    assert "x" * 33 not in r.text and '"input"' not in r.text


@pytest.mark.parametrize(("method", "path", "body"), AUTH_ROUTES)
async def test_body_over_16kb_is_refused_with_413(
    client: TestClient, method: str, path: str, body: dict[str, Any]
) -> None:
    user = await make_user()
    huge = {**body, "padding": "x" * 20_000}
    r = client.request(method, path, json=huge, headers=_auth_headers(path, user))
    assert r.status_code == 413 and r.json() == {"detail": "Request body is too large."}


async def test_a_megabyte_body_is_cut_off_without_being_processed(client: TestClient) -> None:
    r = client.post("/api/auth/login", content=b'{"email": "' + b"a" * 1_000_000 + b'"}')
    assert r.status_code == 413


async def test_chunked_body_without_content_length_is_also_capped(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        yield b'{"email": "a@b.co", "password": "'
        for _ in range(40):
            yield b"x" * 1024
        yield b'"}'

    r = client.post(
        "/api/auth/login", content=chunks(), headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 413


@pytest.mark.parametrize("method_path", [(m, p) for m, p, _ in AUTH_ROUTES])
async def test_normal_sized_requests_are_not_blocked_by_the_cap(
    client: TestClient, method_path: tuple[str, str]
) -> None:
    method, path = method_path
    body = next(b for m, p, b in AUTH_ROUTES if (m, p) == method_path)
    r = client.request(method, path, json=body)
    assert r.status_code != 413


@pytest.mark.parametrize(
    "payload",
    [
        {"email": None, "password": None},
        {"email": ["a@b.co"], "password": {"x": 1}},
        {"email": 12345, "password": 67890},
        {"email": "a@b.co"},
        {},
        {"email": "a@b.co", "password": "x\x00y"},
    ],
)
async def test_odd_login_payloads_never_cause_a_500(
    client: TestClient, payload: dict[str, Any]
) -> None:
    r = client.post("/api/auth/login", json=payload)
    assert r.status_code in (400, 401, 422), r.status_code


async def test_lone_surrogate_in_json_is_not_a_500(client: TestClient) -> None:
    # A JSON escape for a lone surrogate is valid JSON but cannot be encoded as UTF-8.
    # (httpx can't even send it from a dict, so the bodies are raw bytes.)
    headers = {"Content-Type": "application/json"}
    login = rb'{"email": "a\ud800@x.io", "password": "Zr8!kQ2mXv"}'
    assert client.post("/api/auth/login", content=login, headers=headers).status_code in (401, 422)
    signup = rb'{"username": "abc", "email": "a@x.io", "password": "Ab1!\ud800xxxx"}'
    assert client.post("/api/auth/signup", content=signup, headers=headers).status_code in (
        400,
        422,
    )


async def test_exact_maximum_lengths_still_reach_the_business_rules(client: TestClient) -> None:
    # at the schema limit the request is parsed and the friendly 400 from validators.py answers
    r = client.post(
        "/api/auth/signup",
        json={"username": "u" * 32, "email": OK_EMAIL, "password": STRONG},
    )
    assert r.status_code == 400 and "3-8" in r.json()["detail"]
    r = client.post(
        "/api/auth/login", json={"email": "a" * 242 + "@example.io", "password": "p" * 128}
    )
    assert r.status_code == 401


async def test_non_json_and_wrong_types_are_422_not_500(client: TestClient) -> None:
    bad_json = client.post(
        "/api/auth/login", content=b"not json", headers={"Content-Type": "application/json"}
    )
    assert bad_json.status_code == 422
    assert client.post("/api/auth/login", json=["a", "b"]).status_code == 422


async def test_validation_errors_never_echo_what_was_sent(client: TestClient) -> None:
    secret = "MyS3cret!Pass" + "z" * 130  # too long -> 422
    r = client.post("/api/auth/login", json={"email": OK_EMAIL, "password": secret})
    assert r.status_code == 422
    assert "MyS3cret" not in r.text and "input" not in {k for e in r.json()["detail"] for k in e}
    for entry in r.json()["detail"]:
        assert set(entry) == {"loc", "msg", "type"}
