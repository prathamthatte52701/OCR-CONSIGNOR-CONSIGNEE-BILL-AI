"""T3: admin approve / reject(revoke) / re-approve / delete, status filter, audit trail.
Uses REAL signed tokens for real admin/user documents (no dependency overrides)."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.core.security import hash_password, sign_token
from app.main import app
from testkit import current_db

PASSWORD = "Str0ng!Passw0rd"  # noqa: S105 - test-only value
REVOKED = "Your access was removed. Contact the admin."


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


async def _make(role: str = "user", status: str | None = "approved") -> dict[str, Any]:
    uid = ObjectId()
    doc: dict[str, Any] = {
        "_id": uid,
        "username": f"u{str(uid)[-6:]}",
        "email": f"appr-{uid}@example.invalid",
        "passwordHash": hash_password(PASSWORD),
        "role": role,
        "tokenVersion": 0,
        "createdAt": datetime.now(UTC),
        "updatedAt": datetime.now(UTC),
    }
    if status is not None:
        doc["status"] = status
    await current_db().users.insert_one(doc)
    doc["headers"] = {"Authorization": f"Bearer {sign_token(str(uid), 0, role)}"}
    return doc


def _login(client: TestClient, user: dict[str, Any]) -> Any:
    return client.post("/api/auth/login", json={"email": user["email"], "password": PASSWORD})


async def test_status_filter_pending_count_and_legacy_as_approved(client: TestClient) -> None:
    admin = await _make("admin")
    pending_a = await _make(status="pending")
    await _make(status="pending")
    rejected = await _make(status="rejected")
    legacy = await _make(status=None)

    body = client.get("/api/admin/users?status=pending", headers=admin["headers"]).json()
    assert body["total"] == 2 and body["pendingCount"] == 2
    assert all(u["status"] == "pending" for u in body["items"])
    assert str(pending_a["_id"]) in {u["id"] for u in body["items"]}

    approved = client.get("/api/admin/users?status=approved", headers=admin["headers"]).json()
    approved_ids = {u["id"] for u in approved["items"]}
    assert str(legacy["_id"]) in approved_ids and str(admin["_id"]) in approved_ids
    assert str(rejected["_id"]) not in approved_ids
    assert approved["total"] == 2  # admin + legacy
    assert client.get("/api/admin/users?status=bogus", headers=admin["headers"]).status_code == 422
    assert client.get("/api/admin/users", headers=admin["headers"]).json()["total"] == 5


async def test_user_listing_never_leaks_password_hashes(client: TestClient) -> None:
    admin = await _make("admin")
    await _make(status="pending")
    r = client.get("/api/admin/users", headers=admin["headers"])
    assert "passwordHash" not in r.text and "$2b$" not in r.text


async def test_approve_lets_user_in_and_is_audited(client: TestClient) -> None:
    admin = await _make("admin")
    user = await _make(status="pending")
    assert _login(client, user).status_code == 403
    r = client.post(f"/api/admin/users/{user['_id']}/approve", headers=admin["headers"])
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert _login(client, user).status_code == 200
    log = await current_db().auditlogs.find_one({"action": "user_approved"})
    assert log is not None and log["userId"] == admin["_id"]
    assert log["context"]["targetUserId"] == str(user["_id"])
    assert log["context"]["previous"] == "pending"


async def test_approve_does_not_bump_token_version(client: TestClient) -> None:
    admin = await _make("admin")
    user = await _make(status="pending")
    client.post(f"/api/admin/users/{user['_id']}/approve", headers=admin["headers"])
    stored = await current_db().users.find_one({"_id": user["_id"]})
    assert stored is not None and stored["tokenVersion"] == 0


async def test_reject_revokes_old_token_and_bumps_version_once(client: TestClient) -> None:
    admin = await _make("admin")
    user = await _make(status="approved")
    assert client.get("/api/auth/me", headers=user["headers"]).status_code == 200
    r = client.post(f"/api/admin/users/{user['_id']}/reject", headers=admin["headers"])
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    stored = await current_db().users.find_one({"_id": user["_id"]})
    assert stored is not None and stored["tokenVersion"] == 1
    # old token is dead (tokenVersion bumped) and, because status is checked first, answers with
    # the clear 403 "not approved" message; a fresh login gets the same 403.
    old = client.get("/api/auth/me", headers=user["headers"])
    assert old.status_code == 403 and old.json()["detail"]["message"] == REVOKED
    login = _login(client, user)
    assert login.status_code == 403 and login.json()["detail"]["message"] == REVOKED
    assert "token" not in login.text
    log = await current_db().auditlogs.find_one({"action": "user_rejected"})
    assert log is not None and log["context"]["previous"] == "approved"


async def test_pending_user_can_be_rejected_directly(client: TestClient) -> None:
    admin = await _make("admin")
    user = await _make(status="pending")
    r = client.post(f"/api/admin/users/{user['_id']}/reject", headers=admin["headers"])
    assert r.status_code == 200 and r.json()["status"] == "rejected"


async def test_admins_and_the_acting_admin_cannot_be_rejected(client: TestClient) -> None:
    admin = await _make("admin")
    other_admin = await _make("admin")
    own = client.post(f"/api/admin/users/{admin['_id']}/reject", headers=admin["headers"])
    assert own.status_code == 400
    other = client.post(f"/api/admin/users/{other_admin['_id']}/reject", headers=admin["headers"])
    assert other.status_code == 403  # the admin-vs-admin guard answers first
    stored = await current_db().users.find_one({"_id": other_admin["_id"]})
    assert stored is not None and stored["status"] == "approved" and stored["tokenVersion"] == 0
    assert client.get("/api/auth/me", headers=other_admin["headers"]).status_code == 200
    assert await current_db().auditlogs.count_documents({"action": "user_rejected"}) == 0


async def test_reapprove_rejected_then_delete(client: TestClient) -> None:
    admin = await _make("admin")
    user = await _make(status="rejected")
    assert _login(client, user).status_code == 403
    approve = client.post(f"/api/admin/users/{user['_id']}/approve", headers=admin["headers"])
    assert approve.status_code == 200
    assert _login(client, user).status_code == 200
    delete = client.delete(f"/api/admin/users/{user['_id']}", headers=admin["headers"])
    assert delete.status_code == 200
    assert await current_db().users.count_documents({"_id": user["_id"]}) == 0


async def test_rejected_email_cannot_sign_up_again(client: TestClient) -> None:
    user = await _make(status="rejected")
    r = client.post(
        "/api/auth/signup",
        json={"username": "again", "email": user["email"], "password": PASSWORD},
    )
    assert r.status_code == 400
    assert await current_db().users.count_documents({"email": user["email"]}) == 1


async def test_approve_and_reject_are_idempotent(client: TestClient) -> None:
    admin = await _make("admin")
    user = await _make(status="approved")
    for _ in range(2):
        url = f"/api/admin/users/{user['_id']}/approve"
        assert client.post(url, headers=admin["headers"]).status_code == 200
    for _ in range(2):
        url = f"/api/admin/users/{user['_id']}/reject"
        assert client.post(url, headers=admin["headers"]).status_code == 200
    stored = await current_db().users.find_one({"_id": user["_id"]})
    assert stored is not None and stored["status"] == "rejected"


async def test_non_admin_and_anonymous_cannot_use_approval_routes(client: TestClient) -> None:
    plain = await _make()
    target = await _make(status="pending")
    for action in ("approve", "reject"):
        url = f"/api/admin/users/{target['_id']}/{action}"
        assert client.post(url, headers=plain["headers"]).status_code == 403
        assert client.post(url).status_code == 401
    listing = client.get("/api/admin/users?status=pending", headers=plain["headers"])
    assert listing.status_code == 403
    stored = await current_db().users.find_one({"_id": target["_id"]})
    assert stored is not None and stored["status"] == "pending"


async def test_rejected_admin_loses_admin_access_immediately(client: TestClient) -> None:
    admin = await _make("admin")
    await current_db().users.update_one({"_id": admin["_id"]}, {"$set": {"status": "rejected"}})
    assert client.get("/api/admin/users", headers=admin["headers"]).status_code == 403


@pytest.mark.parametrize(
    ("path_id", "expected"),
    [("000000000000000000000000", 404), ("not-an-id", 400), ("123", 400), ("%20", 400)],
)
async def test_unknown_and_malformed_ids(client: TestClient, path_id: str, expected: int) -> None:
    admin = await _make("admin")
    for action in ("approve", "reject"):
        r = client.post(f"/api/admin/users/{path_id}/{action}", headers=admin["headers"])
        assert r.status_code == expected, (action, path_id)


# ------------------------------------------------------------------ Feature 10 follow-up


async def test_re_reject_keeps_first_decision_and_replaces_only_a_new_reason(
    client: TestClient,
) -> None:
    admin, user = await _make("admin"), await _make(status="pending")
    url = f"/api/admin/users/{user['_id']}/reject"
    first = client.post(url, json={"reason": "Wrong email"}, headers=admin["headers"])
    assert first.status_code == 200
    stored = await current_db().users.find_one({"_id": user["_id"]})
    assert stored is not None
    decided_at = stored["decidedAt"]

    again = client.post(url, headers=admin["headers"])  # no new reason
    assert again.status_code == 200
    stored = await current_db().users.find_one({"_id": user["_id"]})
    assert stored is not None
    assert stored["decisionReason"] == "Wrong email" and stored["decidedAt"] == decided_at
    assert stored["decision"] == "rejected" and stored["tokenVersion"] == 2  # bumped each time

    client.post(url, json={"reason": "Duplicate account"}, headers=admin["headers"])
    stored = await current_db().users.find_one({"_id": user["_id"]})
    assert stored is not None
    assert stored["decisionReason"] == "Duplicate account" and stored["decidedAt"] == decided_at


async def test_admin_cannot_demote_self_but_can_edit_and_promote(client: TestClient) -> None:
    admin, plain = await _make("admin"), await _make()
    own = f"/api/admin/users/{admin['_id']}"
    demote = client.patch(own, json={"role": "user"}, headers=admin["headers"])
    assert demote.status_code == 400
    assert demote.json()["detail"] == "You cannot remove your own admin role."
    stored = await current_db().users.find_one({"_id": admin["_id"]})
    assert stored is not None and stored["role"] == "admin"

    rename = client.patch(own, json={"username": "renamed"}, headers=admin["headers"])
    assert rename.status_code == 200 and rename.json()["username"] == "renamed"
    promote = client.patch(
        f"/api/admin/users/{plain['_id']}", json={"role": "admin"}, headers=admin["headers"]
    )
    assert promote.status_code == 200 and promote.json()["role"] == "admin"


async def test_first_time_reject_and_revoke_set_the_decision(client: TestClient) -> None:
    admin = await _make("admin")
    pending, approved = await _make(status="pending"), await _make()
    first = client.post(f"/api/admin/users/{pending['_id']}/reject", headers=admin["headers"])
    assert first.json()["decision"] == "rejected" and first.json()["decidedAt"]
    revoked = client.post(f"/api/admin/users/{approved['_id']}/reject", headers=admin["headers"])
    assert revoked.json()["decision"] == "revoked" and revoked.json()["decidedAt"]
