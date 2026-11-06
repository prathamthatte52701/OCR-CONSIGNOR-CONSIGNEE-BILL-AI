from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings
from app.features.auth.dependencies import CurrentUser, get_current_user
from app.main import app

# Real dev Mongo per .env, same pattern as documents/test_router.py / admin/test_nuke.py: every
# seeded user/log uses a randomly generated id so this can never touch real data, and every
# inserted auditlogs row is deleted again in the autouse cleanup fixture below. The route under
# test (GET /api/auth/me/activity) never reads app.db.users - it trusts the get_current_user
# dependency override entirely, so these tests don't need real user documents at all.


def _user() -> CurrentUser:
    uid = ObjectId()
    return CurrentUser(
        id=uid,
        username=f"actuser{uid}"[:8],
        email=f"activity-test-{uid}@example.invalid",
        role="user",
        token_version=0,
    )


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)


def _act_as(user: CurrentUser) -> None:
    app.dependency_overrides[get_current_user] = lambda: user


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
    if user_ids:
        await db.auditlogs.delete_many({"userId": {"$in": user_ids}})


def _seed_logs(user_id: ObjectId, count: int, action: str = "login") -> list[dict]:
    base = datetime.now(UTC)
    return [
        {
            "userId": user_id,
            "action": action,
            "context": {"i": i},
            "createdAt": base - timedelta(seconds=i),  # i=0 is newest
        }
        for i in range(count)
    ]


async def test_activity_returns_only_callers_own_entries(
    db: AsyncIOMotorDatabase, client: TestClient, _cleanup: list[ObjectId]
) -> None:
    user_a, user_b = _user(), _user()
    _cleanup.extend([user_a.id, user_b.id])
    await db.auditlogs.insert_many(_seed_logs(user_a.id, 3, "document_uploaded"))
    await db.auditlogs.insert_many(_seed_logs(user_b.id, 5, "login"))

    _act_as(user_a)
    resp = client.get("/api/auth/me/activity")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert all(item["action"] == "document_uploaded" for item in body["items"])


async def test_zero_activity_user_gets_empty_items_not_error(
    client: TestClient, _cleanup: list[ObjectId]
) -> None:
    user = _user()
    _cleanup.append(user.id)  # nothing seeded for this user

    _act_as(user)
    resp = client.get("/api/auth/me/activity")
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "total": 0, "page": 1, "limit": 40}


async def test_pagination_covers_all_entries_with_no_gaps_or_duplicates(
    db: AsyncIOMotorDatabase, client: TestClient, _cleanup: list[ObjectId]
) -> None:
    user = _user()
    _cleanup.append(user.id)
    await db.auditlogs.insert_many(_seed_logs(user.id, 85))

    _act_as(user)
    seen_ids: set[str] = set()
    for page in (1, 2, 3):
        resp = client.get("/api/auth/me/activity", params={"page": page, "limit": 40})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 85
        for item in body["items"]:
            assert item["id"] not in seen_ids  # no duplicates across pages
            seen_ids.add(item["id"])

    assert len(seen_ids) == 85  # no gaps either


async def test_default_page_size_is_40(
    db: AsyncIOMotorDatabase, client: TestClient, _cleanup: list[ObjectId]
) -> None:
    user = _user()
    _cleanup.append(user.id)
    await db.auditlogs.insert_many(_seed_logs(user.id, 45))

    _act_as(user)
    resp = client.get("/api/auth/me/activity")
    assert resp.status_code == 200
    body = resp.json()
    assert body["limit"] == 40
    assert len(body["items"]) == 40


async def test_custom_limit_is_respected(
    db: AsyncIOMotorDatabase, client: TestClient, _cleanup: list[ObjectId]
) -> None:
    user = _user()
    _cleanup.append(user.id)
    await db.auditlogs.insert_many(_seed_logs(user.id, 15))

    _act_as(user)
    resp = client.get("/api/auth/me/activity", params={"limit": 10})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 10
    assert body["total"] == 15


async def test_results_sorted_newest_first(
    db: AsyncIOMotorDatabase, client: TestClient, _cleanup: list[ObjectId]
) -> None:
    user = _user()
    _cleanup.append(user.id)
    # _seed_logs makes i=0 the newest (base - 0 seconds); insert out of order on purpose.
    logs = _seed_logs(user.id, 10)
    await db.auditlogs.insert_many([logs[3], logs[0], logs[9], logs[1]])

    _act_as(user)
    resp = client.get("/api/auth/me/activity")
    assert resp.status_code == 200
    items = resp.json()["items"]
    timestamps = [item["createdAt"] for item in items]
    assert timestamps == sorted(timestamps, reverse=True)


async def test_userid_query_param_is_ignored_and_cannot_leak_other_users_data(
    db: AsyncIOMotorDatabase, client: TestClient, _cleanup: list[ObjectId]
) -> None:
    user_a, user_b = _user(), _user()
    _cleanup.extend([user_a.id, user_b.id])
    await db.auditlogs.insert_many(_seed_logs(user_a.id, 2, "login"))
    await db.auditlogs.insert_many(_seed_logs(user_b.id, 7, "document_uploaded"))

    _act_as(user_a)
    # Attempt to override scope via a query param the route doesn't even declare.
    resp = client.get("/api/auth/me/activity", params={"userId": str(user_b.id)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2  # still only user A's own count, param silently ignored


async def test_invalid_page_or_limit_returns_422(
    client: TestClient, _cleanup: list[ObjectId]
) -> None:
    user = _user()
    _cleanup.append(user.id)
    _act_as(user)

    assert client.get("/api/auth/me/activity", params={"page": 0}).status_code == 422
    assert client.get("/api/auth/me/activity", params={"limit": 0}).status_code == 422
    assert client.get("/api/auth/me/activity", params={"limit": 101}).status_code == 422


async def test_unauthenticated_request_is_rejected(client: TestClient) -> None:
    app.dependency_overrides.pop(get_current_user, None)
    try:
        resp = client.get("/api/auth/me/activity")
        assert resp.status_code == 401
    finally:
        pass  # each test re-sets the override via _act_as before making its own requests


# ------------------------------------------------------------------ Feature 9: type filter + join


async def _log(db: AsyncIOMotorDatabase, user_id: ObjectId, action: str, **ctx: object) -> None:
    await db.auditlogs.insert_one(
        {"userId": user_id, "action": action, "context": ctx, "createdAt": datetime.now(UTC)}
    )


async def _doc(db: AsyncIOMotorDatabase, user_id: ObjectId, **fields: str) -> ObjectId:
    res = await db.documents.insert_one({"userId": user_id, "uploadStatus": "processed", **fields})
    return res.inserted_id


async def test_type_filter_and_internal_actions_hidden(
    db: AsyncIOMotorDatabase, client: TestClient, _cleanup: list[ObjectId]
) -> None:
    user = _user()
    _cleanup.append(user.id)
    for action in ("document_uploaded", "documents_download_all", "login", "password_change"):
        await _log(db, user.id, action)
    await _log(db, user.id, "admin_viewed_document")
    _act_as(user)

    def actions(**params: str) -> set[str]:
        r = client.get("/api/auth/me/activity", params=params)
        assert r.status_code == 200
        return {i["action"] for i in r.json()["items"]}

    assert actions(type="documents") == {"document_uploaded", "documents_download_all"}
    assert actions(type="account") == {"login", "password_change"}
    assert "admin_viewed_document" not in actions()  # default = all
    assert len(actions(type="all")) == 4
    assert client.get("/api/auth/me/activity", params={"type": "nope"}).status_code == 422


async def test_document_join_and_context_trim(
    db: AsyncIOMotorDatabase, client: TestClient, _cleanup: list[ObjectId]
) -> None:
    user = _user()
    _cleanup.append(user.id)
    doc_id = await _doc(db, user.id, invoiceNo="INV-9", consignee="ACME", consigneeCode="42")
    await _log(
        db, user.id, "document_corrected", documentId=str(doc_id), field="consignee",
        byAdmin=True, secret="x",
    )  # fmt: skip
    _act_as(user)
    try:
        item = client.get("/api/auth/me/activity").json()["items"][0]
        assert item["document"] == {
            "id": str(doc_id), "invoiceNo": "INV-9", "consigneeCode": "42", "consignee": "ACME",
        }  # fmt: skip
        assert item["context"] == {"documentId": str(doc_id), "field": "consignee"}
    finally:
        await db.documents.delete_one({"_id": doc_id})


async def test_other_users_document_and_bad_id_do_not_leak_or_crash(
    db: AsyncIOMotorDatabase, client: TestClient, _cleanup: list[ObjectId]
) -> None:
    me, other = _user(), _user()
    _cleanup.extend([me.id, other.id])
    theirs = await _doc(db, other.id, invoiceNo="SECRET", consignee="THEM")
    await _log(db, me.id, "document_reprocessed", documentId=str(theirs))
    await _log(db, me.id, "document_reprocessed", documentId="not-an-object-id")
    _act_as(me)
    try:
        r = client.get("/api/auth/me/activity")
        assert r.status_code == 200
        assert [i["document"] for i in r.json()["items"]] == [None, None]
        assert "SECRET" not in r.text
    finally:
        await db.documents.delete_one({"_id": theirs})


async def test_delete_route_logs_name_and_activity_shows_it(
    db: AsyncIOMotorDatabase, client: TestClient, _cleanup: list[ObjectId]
) -> None:
    user = _user()
    _cleanup.append(user.id)
    doc_id = await _doc(db, user.id, invoiceNo="GONE-1", consignee="X" * 150)
    _act_as(user)
    assert client.delete(f"/api/documents/{doc_id}").status_code == 200
    item = client.get("/api/auth/me/activity").json()["items"][0]
    assert item["action"] == "document_deleted"
    assert item["document"] is None
    assert item["context"]["invoiceNo"] == "GONE-1"
    assert item["context"]["consignee"] == "X" * 100
