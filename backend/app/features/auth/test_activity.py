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
    assert all(item["userId"] == str(user_a.id) for item in body["items"])
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
    assert all(item["userId"] == str(user_a.id) for item in body["items"])


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
