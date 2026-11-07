"""Admin-handled password reset: public request, admin temp password, forced change, dismiss and
auto-close, old self-service routes gone. In-process fake Mongo, random users via testkit."""

from datetime import UTC, datetime
from typing import Any

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.main import app
from testkit import PASSWORD, current_db, make_user

REQUEST = "/api/auth/password-reset-request"
TEMP = "Tmp#Pass9word"  # noqa: S105 - test-only value
NEW = "Brand!New7Pass"  # noqa: S105 - test-only value


@pytest.fixture(scope="module")
def client() -> Any:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


async def open_request(user: dict[str, Any]) -> ObjectId:
    res = await current_db().passwordresetrequests.insert_one(
        {
            "userId": user["_id"],
            "email": user["email"],
            "username": user["username"],
            "note": "",
            "status": "open",
            "createdAt": datetime.now(UTC),
            "updatedAt": datetime.now(UTC),
        }
    )
    return res.inserted_id  # type: ignore[no-any-return]


def temp_url(request_id: ObjectId, action: str = "temp-password") -> str:
    return f"/api/admin/password-requests/{request_id}/{action}"


def login(client: TestClient, user: dict[str, Any], password: str = PASSWORD) -> Any:
    return client.post("/api/auth/login", json={"email": user["email"], "password": password})


async def rows_for(user: dict[str, Any]) -> list[dict[str, Any]]:
    cursor = current_db().passwordresetrequests.find({"userId": user["_id"]})
    return [r async for r in cursor]


# ------------------------------------------------------------------ 1. public request


async def test_public_request_is_uniform_and_keeps_one_open_row(client: TestClient) -> None:
    eligible, pending = await make_user(), await make_user(status="pending")
    admin = await make_user(role="admin")
    ghost = f"ghost-{ObjectId()}@example.invalid"
    answers = [
        client.post(REQUEST, json={"email": email})
        for email in (eligible["email"], pending["email"], admin["email"], ghost)
    ]
    assert {(r.status_code, r.text) for r in answers} == {(200, answers[0].text)}
    assert len(await rows_for(eligible)) == 1
    for other in (pending, admin):
        assert await rows_for(other) == []

    noisy = "line\x00one‮" + "x" * 300
    again = client.post(REQUEST, json={"email": eligible["email"], "note": noisy})
    assert again.status_code == 200
    rows = await rows_for(eligible)
    assert len(rows) == 1 and rows[0]["status"] == "open"
    assert "\x00" not in rows[0]["note"] and "‮" not in rows[0]["note"]
    assert len(rows[0]["note"]) == 200


# ------------------------------------------------------------------ 2. temp password


async def test_temp_password_flow_and_guards(client: TestClient) -> None:
    admin, other_admin = await make_user(role="admin"), await make_user(role="admin")
    user, pending = await make_user(), await make_user(status="pending")
    h = admin["headers"]

    weak_id = await open_request(user)
    weak = client.post(temp_url(weak_id), json={"password": "short"}, headers=h)
    assert weak.status_code == 422
    row = await current_db().passwordresetrequests.find_one({"_id": weak_id})
    assert row is not None and row["status"] == "open"  # validated before claiming

    ok = client.post(temp_url(weak_id), json={"password": TEMP}, headers=h)
    assert ok.status_code == 200
    stored = await current_db().users.find_one({"_id": user["_id"]})
    assert stored is not None
    assert stored["mustChangePassword"] is True and stored["tokenVersion"] == 1
    assert login(client, user, TEMP).status_code == 200
    closed = await current_db().passwordresetrequests.find_one({"_id": weak_id})
    assert closed is not None and closed["status"] == "done"
    assert closed["resolution"] == "temp_password"

    again = client.post(temp_url(weak_id), json={"password": TEMP}, headers=h)
    assert again.status_code == 409

    admin_req = await open_request(other_admin)
    pending_req = await open_request(pending)
    assert client.post(temp_url(admin_req), json={"password": TEMP}, headers=h).status_code == 403
    assert client.post(temp_url(pending_req), json={"password": TEMP}, headers=h).status_code == 403
    # a refused attempt must leave the request open
    left = await current_db().passwordresetrequests.find_one({"_id": pending_req})
    assert left is not None and left["status"] == "open"

    logs = [row async for row in current_db().auditlogs.find({})]
    assert any(row["action"] == "password_reset_temp_set" for row in logs)
    assert TEMP not in repr(logs)


# ------------------------------------------------------------------ 3. forced change gate


async def test_flagged_user_is_gated_until_the_password_is_changed(client: TestClient) -> None:
    admin, user = await make_user(role="admin"), await make_user()
    request_id = await open_request(user)
    assert (
        client.post(
            temp_url(request_id), json={"password": TEMP}, headers=admin["headers"]
        ).status_code
        == 200
    )
    token = login(client, user, TEMP).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    blocked = client.get("/api/documents/stats", headers=headers)
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "PASSWORD_CHANGE_REQUIRED"
    assert client.get("/api/auth/me", headers=headers).status_code == 200  # allowed route 1

    changed = client.post(
        "/api/auth/change-password",
        json={"currentPassword": TEMP, "newPassword": NEW},
        headers=headers,
    )  # allowed route 2
    assert changed.status_code == 200
    fresh = {"Authorization": f"Bearer {changed.json()['token']}"}
    assert client.get("/api/documents/stats", headers=fresh).status_code == 200
    stored = await current_db().users.find_one({"_id": user["_id"]})
    assert stored is not None and "mustChangePassword" not in stored
    assert client.get("/api/documents/stats", headers=headers).status_code == 401  # old token dead


# ------------------------------------------------------------------ 4. dismiss + auto-close


async def test_dismiss_and_login_auto_close(client: TestClient) -> None:
    admin, user = await make_user(role="admin"), await make_user()
    request_id = await open_request(user)
    dismissed = client.post(temp_url(request_id, "dismiss"), headers=admin["headers"])
    assert dismissed.status_code == 200
    assert client.post(temp_url(request_id, "dismiss"), headers=admin["headers"]).status_code == 409

    open_id = await open_request(user)
    assert login(client, user).status_code == 200  # the user remembered their own password
    row = await current_db().passwordresetrequests.find_one({"_id": open_id})
    assert row is not None and row["status"] == "done"
    assert row["resolution"] == "user_logged_in"

    flagged = await make_user()
    await current_db().users.update_one(
        {"_id": flagged["_id"]}, {"$set": {"mustChangePassword": True}}
    )
    still_open = await open_request(flagged)
    assert login(client, flagged).status_code == 200  # a login with the temp password
    row = await current_db().passwordresetrequests.find_one({"_id": still_open})
    assert row is not None and row["status"] == "open"


# ------------------------------------------------------------------ 5. old routes + limiter


async def test_old_routes_are_gone_and_the_email_limit_is_uniform(client: TestClient) -> None:
    for path in ("verify", "reset"):
        r = client.post(f"/api/auth/forgot-password/{path}", json={})
        assert r.status_code in (404, 405)

    ghost = f"ghost-{ObjectId()}@example.invalid"
    codes = [client.post(REQUEST, json={"email": ghost}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]  # same limit for an email that does not exist
    real = await make_user()
    real_codes = [client.post(REQUEST, json={"email": real["email"]}).status_code for _ in range(4)]
    assert real_codes == codes
