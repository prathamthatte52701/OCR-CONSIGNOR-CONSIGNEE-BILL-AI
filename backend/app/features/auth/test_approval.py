"""Admin-approval gate: signup -> pending, login/token blocked until approved, admin
approve/reject/revoke, status filter. Same real-dev-Mongo + random-id + cleanup pattern as
test_activity.py - every user is created with a unique random email and deleted afterwards."""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings
from app.core.security import hash_password, sign_token
from app.features.auth.dependencies import (
    CurrentUser,
    get_current_user,
)
from app.main import app

PENDING = "Waiting for admin approval."
REJECTED = "Your request was not approved. Contact the admin."
PASSWORD = "Str0ng!Passw0rd"  # noqa: S105 - test-only value


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
async def db() -> AsyncIterator[AsyncIOMotorDatabase]:
    test_client: AsyncIOMotorClient = AsyncIOMotorClient(settings.mongo_uri, tz_aware=True)
    try:
        yield test_client[settings.mongo_db_name]
    finally:
        test_client.close()


@pytest.fixture(autouse=True)
async def _cleanup(db: AsyncIOMotorDatabase) -> AsyncIterator[list[ObjectId]]:
    user_ids: list[ObjectId] = []
    yield user_ids
    app.dependency_overrides.pop(get_current_user, None)
    if user_ids:
        await db.users.delete_many({"_id": {"$in": user_ids}})
        await db.auditlogs.delete_many({"userId": {"$in": user_ids}})
    await db.users.delete_many({"email": {"$regex": r"^approval-test-.*@example\.invalid$"}})


async def _make_user(
    db: AsyncIOMotorDatabase,
    cleanup: list[ObjectId],
    *,
    status: str | None,
    role: str = "user",
) -> dict[str, Any]:
    uid = ObjectId()
    cleanup.append(uid)
    doc: dict[str, Any] = {
        "_id": uid,
        "username": f"u{str(uid)[-6:]}",
        "email": f"approval-test-{uid}@example.invalid",
        "passwordHash": hash_password(PASSWORD),
        "role": role,
        "tokenVersion": 0,
        "createdAt": datetime.now(UTC),
        "updatedAt": datetime.now(UTC),
    }
    if status is not None:  # None = legacy document with no status field at all
        doc["status"] = status
    await db.users.insert_one(doc)
    return doc


def _login(client: TestClient, user: dict[str, Any], password: str = PASSWORD) -> Any:
    return client.post("/api/auth/login", json={"email": user["email"], "password": password})


def _act_as_admin(cleanup: list[ObjectId]) -> CurrentUser:
    admin = CurrentUser(
        id=ObjectId(), username="admintst", email="a@example.invalid", role="admin", token_version=0
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    return admin


async def test_signup_creates_pending_user(
    client: TestClient, db: AsyncIOMotorDatabase, _cleanup: list[ObjectId]
) -> None:
    email = f"approval-test-{ObjectId()}@example.invalid"
    r = client.post(
        "/api/auth/signup", json={"username": "newbie", "email": email, "password": PASSWORD}
    )
    assert r.status_code == 201
    assert r.json()["message"] == "Account created. Waiting for admin approval."
    created = await db.users.find_one({"email": email})
    assert created is not None and created["status"] == "pending"
    _cleanup.append(created["_id"])


async def test_pending_login_blocked_without_token(
    client: TestClient, db: AsyncIOMotorDatabase, _cleanup: list[ObjectId]
) -> None:
    user = await _make_user(db, _cleanup, status="pending")
    r = _login(client, user)
    assert r.status_code == 403 and r.json()["detail"] == PENDING
    assert "token" not in r.text


async def test_rejected_login_blocked(
    client: TestClient, db: AsyncIOMotorDatabase, _cleanup: list[ObjectId]
) -> None:
    user = await _make_user(db, _cleanup, status="rejected")
    r = _login(client, user)
    assert r.status_code == 403 and r.json()["detail"] == REJECTED


async def test_wrong_password_never_reveals_status(
    client: TestClient, db: AsyncIOMotorDatabase, _cleanup: list[ObjectId]
) -> None:
    user = await _make_user(db, _cleanup, status="pending")
    r = _login(client, user, password="Wr0ng!passw0rd")
    assert r.status_code == 401 and r.json()["detail"] == "Invalid email or password."


async def test_approved_and_legacy_users_can_login(
    client: TestClient, db: AsyncIOMotorDatabase, _cleanup: list[ObjectId]
) -> None:
    for status in ("approved", None):
        user = await _make_user(db, _cleanup, status=status)
        r = _login(client, user)
        assert r.status_code == 200 and r.json()["token"]


@pytest.mark.parametrize(("status", "message"), [("pending", PENDING), ("rejected", REJECTED)])
async def test_old_token_blocked_on_protected_routes(
    client: TestClient,
    db: AsyncIOMotorDatabase,
    _cleanup: list[ObjectId],
    status: str,
    message: str,
) -> None:
    user = await _make_user(db, _cleanup, status=status)
    headers = {"Authorization": f"Bearer {sign_token(str(user['_id']), 0, 'user')}"}
    for path in ("/api/auth/me", "/api/documents"):
        r = client.get(path, headers=headers)
        assert r.status_code == 403 and r.json()["detail"] == message, path


async def test_status_change_takes_effect_on_existing_token(
    client: TestClient, db: AsyncIOMotorDatabase, _cleanup: list[ObjectId]
) -> None:
    user = await _make_user(db, _cleanup, status="approved")
    headers = {"Authorization": f"Bearer {sign_token(str(user['_id']), 0, 'user')}"}
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"status": "rejected"}})
    assert client.get("/api/auth/me", headers=headers).status_code == 403


async def test_admin_approve_lets_user_in_and_is_audited(
    client: TestClient, db: AsyncIOMotorDatabase, _cleanup: list[ObjectId]
) -> None:
    user = await _make_user(db, _cleanup, status="pending")
    assert _login(client, user).status_code == 403
    admin = _act_as_admin(_cleanup)
    r = client.post(f"/api/admin/users/{user['_id']}/approve")
    assert r.status_code == 200 and r.json()["status"] == "approved"
    app.dependency_overrides.pop(get_current_user, None)
    assert _login(client, user).status_code == 200
    log = await db.auditlogs.find_one({"action": "user_approved", "userId": admin.id})
    assert log is not None and log["context"]["targetUserId"] == str(user["_id"])
    await db.auditlogs.delete_many({"userId": admin.id})


async def test_admin_reject_revokes_existing_token(
    client: TestClient, db: AsyncIOMotorDatabase, _cleanup: list[ObjectId]
) -> None:
    user = await _make_user(db, _cleanup, status="approved")
    headers = {"Authorization": f"Bearer {sign_token(str(user['_id']), 0, 'user')}"}
    assert client.get("/api/auth/me", headers=headers).status_code == 200

    admin = _act_as_admin(_cleanup)
    r = client.post(f"/api/admin/users/{user['_id']}/reject")
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    app.dependency_overrides.pop(get_current_user, None)

    # tokenVersion was bumped AND status is checked first -> old token answers 403 "rejected".
    assert client.get("/api/auth/me", headers=headers).status_code == 403
    login = _login(client, user)
    assert login.status_code == 403 and login.json()["detail"] == REJECTED
    await db.auditlogs.delete_many({"userId": admin.id})


async def test_admin_accounts_cannot_be_rejected(
    client: TestClient, db: AsyncIOMotorDatabase, _cleanup: list[ObjectId]
) -> None:
    other_admin = await _make_user(db, _cleanup, status="approved", role="admin")
    _act_as_admin(_cleanup)
    r = client.post(f"/api/admin/users/{other_admin['_id']}/reject")
    assert r.status_code == 400
    stored = await db.users.find_one({"_id": other_admin["_id"]})
    assert stored is not None and stored["status"] == "approved"


async def test_list_users_status_filter_and_pending_count(
    client: TestClient, db: AsyncIOMotorDatabase, _cleanup: list[ObjectId]
) -> None:
    pending = await _make_user(db, _cleanup, status="pending")
    rejected = await _make_user(db, _cleanup, status="rejected")
    legacy = await _make_user(db, _cleanup, status=None)
    _act_as_admin(_cleanup)

    body = client.get("/api/admin/users?status=pending&limit=100").json()
    ids = {item["id"] for item in body["items"]}
    assert str(pending["_id"]) in ids and str(rejected["_id"]) not in ids
    assert all(item["status"] == "pending" for item in body["items"])
    assert body["pendingCount"] >= 1

    approved_ids = {
        item["id"]
        for item in client.get("/api/admin/users?status=approved&limit=100").json()["items"]
    }
    assert str(legacy["_id"]) in approved_ids  # no status field counts as approved
    assert client.get("/api/admin/users?status=bogus").status_code == 422


async def test_non_admin_cannot_use_approval_routes(
    client: TestClient, db: AsyncIOMotorDatabase, _cleanup: list[ObjectId]
) -> None:
    target = await _make_user(db, _cleanup, status="pending")
    plain = CurrentUser(
        id=ObjectId(), username="plain", email="p@example.invalid", role="user", token_version=0
    )
    app.dependency_overrides[get_current_user] = lambda: plain
    for action in ("approve", "reject"):
        assert client.post(f"/api/admin/users/{target['_id']}/{action}").status_code == 403
    assert client.get("/api/admin/users?status=pending").status_code == 403


async def test_unknown_user_and_bad_id(client: TestClient, _cleanup: list[ObjectId]) -> None:
    _act_as_admin(_cleanup)
    zero = "000000000000000000000000"
    assert client.post(f"/api/admin/users/{zero}/approve").status_code == 404
    assert client.post("/api/admin/users/not-an-id/approve").status_code == 400


# --- T1 hardening: fail-closed statuses, migration script, signup race ----------------------


@pytest.mark.parametrize("bad_status", [None, "APPROVED", "Approved ", "banned", 1, ""])
async def test_unknown_or_malformed_status_fails_closed(
    client: TestClient, db: AsyncIOMotorDatabase, _cleanup: list[ObjectId], bad_status: object
) -> None:
    user = await _make_user(db, _cleanup, status="approved")
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"status": bad_status}})
    assert _login(client, user).status_code == 403
    headers = {"Authorization": f"Bearer {sign_token(str(user['_id']), 0, 'user')}"}
    assert client.get("/api/auth/me", headers=headers).status_code == 403


async def test_migration_dry_run_then_real_run_is_idempotent(
    client: TestClient, db: AsyncIOMotorDatabase, _cleanup: list[ObjectId]
) -> None:
    from app.scripts.migrate_user_status import migrate

    legacy = await _make_user(db, _cleanup, status=None)
    pending = await _make_user(db, _cleanup, status="pending")
    rejected = await _make_user(db, _cleanup, status="rejected")

    assert await migrate(dry_run=True, db=db) == 1
    assert "status" not in (await db.users.find_one({"_id": legacy["_id"]}) or {})  # dry run
    assert await migrate(db=db) == 1
    assert (await db.users.find_one({"_id": legacy["_id"]}))["status"] == "approved"  # type: ignore[index]
    assert await migrate(db=db) == 0  # idempotent
    # users that already had a status are never touched
    assert (await db.users.find_one({"_id": pending["_id"]}))["status"] == "pending"  # type: ignore[index]
    assert (await db.users.find_one({"_id": rejected["_id"]}))["status"] == "rejected"  # type: ignore[index]


async def test_double_signup_same_email_creates_exactly_one_user(
    client: TestClient, db: AsyncIOMotorDatabase, _cleanup: list[ObjectId]
) -> None:
    email = f"approval-test-{ObjectId()}@example.invalid"
    body = {"username": "dupe", "email": email, "password": PASSWORD}
    first = client.post("/api/auth/signup", json=body)
    second = client.post("/api/auth/signup", json={**body, "username": "dupe2"})
    assert first.status_code == 201
    assert second.status_code == 400  # generic error, same shape as any signup failure
    assert await db.users.count_documents({"email": email}) == 1
    created = await db.users.find_one({"email": email})
    assert created is not None
    _cleanup.append(created["_id"])


async def test_signup_email_is_case_insensitive_for_duplicates(
    client: TestClient, db: AsyncIOMotorDatabase, _cleanup: list[ObjectId]
) -> None:
    email = f"approval-test-{ObjectId()}@example.invalid"
    assert (
        client.post(
            "/api/auth/signup", json={"username": "casea", "email": email, "password": PASSWORD}
        ).status_code
        == 201
    )
    again = client.post(
        "/api/auth/signup",
        json={"username": "caseb", "email": email.upper(), "password": PASSWORD},
    )
    assert again.status_code == 400
    created = await db.users.find_one({"email": email})
    assert created is not None
    _cleanup.append(created["_id"])


async def test_signup_cannot_self_assign_status_or_role(
    client: TestClient, db: AsyncIOMotorDatabase, _cleanup: list[ObjectId]
) -> None:
    email = f"approval-test-{ObjectId()}@example.invalid"
    r = client.post(
        "/api/auth/signup",
        json={
            "username": "sneaky",
            "email": email,
            "password": PASSWORD,
            "status": "approved",
            "role": "admin",
        },
    )
    assert r.status_code == 201
    created = await db.users.find_one({"email": email})
    assert created is not None
    _cleanup.append(created["_id"])
    assert created["status"] == "pending" and created["role"] == "user"
