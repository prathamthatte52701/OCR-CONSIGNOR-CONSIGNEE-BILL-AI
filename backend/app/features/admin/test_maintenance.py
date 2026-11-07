"""Feature 13: maintenance page data, age-based purge (per user + global) and admin email edit.
In-process fake Mongo; users and documents come from testkit with random ids."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from testkit import PASSWORD, current_db, make_document, make_user

OLD = datetime.now(UTC) - timedelta(days=400)
BODY = {"password": PASSWORD, "confirmPassword": PASSWORD, "confirmationPhrase": "NUKE USER"}
GLOBAL_BODY = {**BODY, "confirmationPhrase": "NUKE ALL"}


@pytest.fixture(scope="module")
def client() -> Any:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def purge(client: TestClient, url: str, admin: dict[str, Any], body: dict[str, Any]) -> Any:
    return client.request("DELETE", url, json=body, headers=admin["headers"])


async def stored_files() -> int:
    return await current_db()["fs.files"].count_documents({})


# ---------------------------------------------------------------- maintenance page


async def test_system_admin_only_no_secrets_works_empty(client: TestClient) -> None:
    user, admin = await make_user(), await make_user(role="admin")
    assert client.get("/api/admin/system", headers=user["headers"]).status_code == 403
    assert client.get("/api/admin/system").status_code in (401, 403)

    res = client.get("/api/admin/system", headers=admin["headers"])
    assert res.status_code == 200
    data = res.json()
    assert data["db"]["ok"] is True and data["storage"] == {"files": 0, "bytes": 0}
    assert data["documentsProcessed"] == 0 and data["orphanedFiles"] == 0
    assert settings.mongo_uri not in res.text and "mongodb" not in res.text.lower()
    assert (
        client.get("/api/admin/maintenance-activity", headers=admin["headers"]).status_code == 200
    )


# ---------------------------------------------------------------- age-based purge


async def test_purge_rejects_other_month_values(client: TestClient) -> None:
    admin = await make_user(role="admin")
    owner = await make_user()
    for months in (0, 4, 5, 12, -1):
        url = f"/api/admin/users/{owner['id']}/purge-months?months={months}"
        assert purge(client, url, admin, BODY).status_code == 400
        assert (
            client.get(
                f"/api/admin/purge-months/preview?months={months}", headers=admin["headers"]
            ).status_code
            == 400
        )
    assert purge(client, "/api/admin/purge-months?months=7", admin, GLOBAL_BODY).status_code == 400


async def test_user_purge_is_scoped_removes_files_and_needs_confirmation(
    client: TestClient,
) -> None:
    admin, owner, other = await make_user(role="admin"), await make_user(), await make_user()
    old = await make_document(owner["_id"], createdAt=OLD)
    fresh = await make_document(owner["_id"])
    others_old = await make_document(other["_id"], createdAt=OLD)
    assert await stored_files() == 6
    url = f"/api/admin/users/{owner['id']}/purge-months?months=3"

    preview = client.get(
        f"/api/admin/purge-months/preview?months=3&userId={owner['id']}", headers=admin["headers"]
    )
    assert preview.json()["documents"] == 1  # dry run: nothing deleted yet
    assert await current_db().documents.count_documents({}) == 3

    for bad in ({**BODY, "confirmationPhrase": "nope"}, {**BODY, "confirmPassword": "x"}):
        assert purge(client, url, admin, bad).status_code == 400
    assert (
        purge(
            client,
            url,
            admin,
            {**BODY, "password": "Wrong!Pass1", "confirmPassword": "Wrong!Pass1"},
        ).status_code
        == 400
    )
    assert await current_db().documents.count_documents({}) == 3  # refused: untouched

    res = purge(client, url, admin, BODY)
    assert res.status_code == 200 and res.json()["deletedCount"] == 1
    db = current_db()
    assert await db.documents.find_one({"_id": old["_id"]}) is None
    assert await db.documents.find_one({"_id": fresh["_id"]}) is not None
    assert await db.documents.find_one({"_id": others_old["_id"]}) is not None
    assert await stored_files() == 4  # the two files of the purged document are really gone

    row = await db.auditlogs.find_one({"action": "admin_nuke_attempt", "context.reason": "success"})
    assert row is not None and row["context"]["deletedCount"] == 1
    assert PASSWORD not in str(row)


async def test_global_purge_leaves_users_and_audit_log(client: TestClient) -> None:
    admin, owner = await make_user(role="admin"), await make_user()
    old = await make_document(owner["_id"], createdAt=OLD)
    fresh = await make_document(owner["_id"])
    db = current_db()
    await db.auditlogs.insert_one(
        {"userId": owner["_id"], "action": "login", "context": {}, "createdAt": OLD}
    )
    users_before, logs_before = await db.users.count_documents(
        {}
    ), await db.auditlogs.count_documents({})

    res = purge(client, "/api/admin/purge-months?months=6", admin, GLOBAL_BODY)
    assert res.status_code == 200 and res.json()["deletedCount"] == 1
    assert await db.documents.find_one({"_id": old["_id"]}) is None
    assert await db.documents.find_one({"_id": fresh["_id"]}) is not None
    assert await db.users.count_documents({}) == users_before
    assert await db.auditlogs.count_documents({}) == logs_before + 1  # only the purge entry
    assert await stored_files() == 2
    # the user phrase does not open the global purge
    assert purge(client, "/api/admin/purge-months?months=6", admin, BODY).status_code == 400


async def test_purge_shares_the_nuke_rate_limit(client: TestClient) -> None:
    admin = await make_user(role="admin")
    bad = {**GLOBAL_BODY, "confirmationPhrase": "nope"}
    for _ in range(5):
        assert purge(client, "/api/admin/purge-months?months=1", admin, bad).status_code == 400
    assert purge(client, "/api/admin/purge-months?months=1", admin, GLOBAL_BODY).status_code == 429


# ---------------------------------------------------------------- admin email edit


async def test_email_edit_rules_and_effects(client: TestClient) -> None:
    admin, other_admin = await make_user(role="admin"), await make_user(role="admin")
    user, taken = await make_user(), await make_user()
    url = f"/api/admin/users/{user['id']}/email"

    def put(target: str, email: str) -> Any:
        return client.put(
            f"/api/admin/users/{target}/email", json={"email": email}, headers=admin["headers"]
        )

    assert put(user["id"], taken["email"].upper()).status_code == 400  # duplicate, other case
    assert put(admin["id"], "me@example.invalid").status_code == 400  # own email
    assert put(other_admin["id"], "x@example.invalid").status_code == 403  # admin vs admin
    assert put(user["id"], "not-an-email").status_code == 400
    assert (
        client.put(url, json={"email": "a@example.invalid"}, headers=user["headers"]).status_code
        == 403
    )

    new = f"  New-{user['id']}@Example.Invalid "
    res = put(user["id"], new)
    assert res.status_code == 200 and res.json()["email"] == new.strip().lower()
    db = current_db()
    assert (await db.users.find_one({"_id": user["_id"]}))["tokenVersion"] == 1
    assert client.get("/api/auth/me", headers=user["headers"]).status_code == 401  # signed out

    rows = [r async for r in db.auditlogs.find({"action": {"$regex": "email"}})]
    assert {r["action"] for r in rows} == {"email_changed_by_admin", "admin_changed_user_email"}
    assert PASSWORD not in str(rows) and "passwordHash" not in str(rows)

    first = client.post("/api/auth/login", json={"email": new.strip(), "password": PASSWORD})
    again = client.post("/api/auth/login", json={"email": new.strip(), "password": PASSWORD})
    assert first.json()["emailChanged"] is True and again.json()["emailChanged"] is False
    token = {"Authorization": f"Bearer {first.json()['token']}"}
    activity = client.get("/api/auth/me/activity?type=account", headers=token).json()["items"]
    assert any(i["action"] == "email_changed_by_admin" for i in activity)


async def test_patch_no_longer_changes_email(client: TestClient) -> None:
    admin, user = await make_user(role="admin"), await make_user()
    res = client.patch(
        f"/api/admin/users/{user['id']}",
        json={"email": "other@example.invalid", "username": "renamed"},
        headers=admin["headers"],
    )
    assert res.status_code == 400 and "change-email" in res.json()["detail"]
    stored = await current_db().users.find_one({"_id": user["_id"]})
    assert stored["email"] == user["email"] and stored["username"] == user["username"]


async def test_email_change_syncs_only_the_open_reset_request(client: TestClient) -> None:
    admin, user, other = await make_user(role="admin"), await make_user(), await make_user()
    now = datetime.now(UTC)
    db = current_db()

    def row(owner: dict[str, Any], status: str) -> dict[str, Any]:
        return {"userId": owner["_id"], "email": owner["email"], "status": status, "createdAt": now}

    await db.passwordresetrequests.insert_one(row(user, "done"))
    await db.passwordresetrequests.insert_one(row(user, "open"))
    await db.passwordresetrequests.insert_one(row(other, "open"))
    new = f"synced-{user['id']}@example.invalid"
    res = client.put(
        f"/api/admin/users/{user['id']}/email", json={"email": new}, headers=admin["headers"]
    )
    assert res.status_code == 200
    mine = {
        r["status"]: r["email"]
        async for r in db.passwordresetrequests.find({"userId": user["_id"]})
    }
    assert mine == {"open": new, "done": user["email"]}
    theirs = await db.passwordresetrequests.find_one({"userId": other["_id"]})
    assert theirs["email"] == other["email"]
