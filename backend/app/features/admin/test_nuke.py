from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

import app.features.admin.router as admin_router
from app.core.config import settings
from app.core.security import hash_password
from app.features.auth.dependencies import CurrentUser, get_current_user
from app.main import app

# Real dev Mongo per .env. IMPORTANT SAFETY NOTE: "global" nuke tests never use olderThanMonths
# (relative to "now") against the live shared database - that could delete real documents older
# than the cutoff. Every global-scope test below uses an explicit `year` far enough in the past
# (2000) that only this file's own seeded data can ever match. User-scoped tests are safe with
# relative dates since they're additionally filtered by a randomly generated test-only userId.

_SAFE_PAST_YEAR = 2000


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
async def db() -> AsyncIterator[AsyncIOMotorDatabase]:
    test_client: AsyncIOMotorClient = AsyncIOMotorClient(settings.mongo_uri, tz_aware=True)
    try:
        yield test_client[settings.mongo_db_name]
    finally:
        test_client.close()


@pytest.fixture
async def admin_actor(
    db: AsyncIOMotorDatabase, client: TestClient
) -> AsyncIterator[tuple[ObjectId, str]]:
    """A fresh admin user + known password for exactly one test, isolated from every other
    test's nuke rate-limit budget (which is keyed by admin id, 24h rolling window)."""
    admin_id = ObjectId()
    password = "NukeTestAdminPw1!"
    now = datetime.now(UTC)
    await db.users.insert_one(
        {
            "_id": admin_id,
            "username": "nuketestadm",
            "email": f"nuke-admin-{admin_id}@example.invalid",
            "passwordHash": hash_password(password),
            "role": "admin",
            "tokenVersion": 0,
            "createdAt": now,
            "updatedAt": now,
        }
    )

    def _fake_admin() -> CurrentUser:
        return CurrentUser(
            id=admin_id,
            username="nuketestadm",
            email=f"nuke-admin-{admin_id}@example.invalid",
            role="admin",
            token_version=0,
        )

    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = _fake_admin
    try:
        yield admin_id, password
    finally:
        if previous is not None:
            app.dependency_overrides[get_current_user] = previous
        else:
            app.dependency_overrides.pop(get_current_user, None)
        await db.users.delete_one({"_id": admin_id})
        await db.auditlogs.delete_many({"userId": admin_id})


@pytest.fixture(autouse=True)
async def _cleanup(db: AsyncIOMotorDatabase) -> AsyncIterator[list[ObjectId]]:
    user_ids: list[ObjectId] = []
    yield user_ids
    if user_ids:
        await db.users.delete_many({"_id": {"$in": user_ids}})
        await db.documents.delete_many({"userId": {"$in": user_ids}})
        await db.corrections.delete_many({"userId": {"$in": user_ids}})


def _seed_user(**overrides: object) -> dict[str, Any]:
    now = datetime.now(UTC)
    doc = {
        "username": "nuketarget",
        "email": f"nuke-target-{ObjectId()}@example.invalid",
        "passwordHash": "not-a-real-hash",
        "role": "user",
        "tokenVersion": 0,
        "createdAt": now,
        "updatedAt": now,
    }
    doc.update(overrides)
    return doc


def _seed_doc(user_id: ObjectId, **overrides: object) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "userId": user_id,
        "uploadStatus": "processed",
        "invoiceNo": "NUKE-TEST",
    }
    doc.update(overrides)
    return doc


# --- _build_range_filter: pure logic, no DB - proves global mode never adds a userId key ----


def test_build_range_filter_global_age_based_omits_user_id() -> None:
    query = admin_router._build_range_filter(None, 9, None, None)
    assert "userId" not in query
    assert "$lt" in query["createdAt"]


def test_build_range_filter_user_scoped_includes_user_id() -> None:
    uid = ObjectId()
    query = admin_router._build_range_filter(uid, 9, None, None)
    assert query["userId"] == uid


def test_build_range_filter_rejects_both_older_than_months_and_year() -> None:
    with pytest.raises(Exception):  # noqa: B017 - HTTPException, validated at the route layer
        admin_router._build_range_filter(None, 9, 2025, None)


def test_build_range_filter_rejects_month_without_year() -> None:
    with pytest.raises(Exception):  # noqa: B017
        admin_router._build_range_filter(None, None, None, 6)


# --- User-scoped nuke: age-based and Year+Month, safe (scoped to a random test-only userId) --


async def test_nuke_user_age_based_deletes_only_matching_range(
    db: AsyncIOMotorDatabase, client: TestClient, admin_actor: tuple[ObjectId, str], _cleanup: list
) -> None:
    _admin_id, password = admin_actor
    target = await db.users.insert_one(_seed_user())
    target_id = target.inserted_id
    _cleanup.append(target_id)
    now = datetime.now(UTC)
    await db.documents.insert_many(
        [
            _seed_doc(target_id, createdAt=now - timedelta(days=400), invoiceNo="OLD-1"),
            _seed_doc(target_id, createdAt=now - timedelta(days=200), invoiceNo="OLD-2"),
            _seed_doc(target_id, createdAt=now - timedelta(days=30), invoiceNo="RECENT"),
        ]
    )

    resp = client.post(
        f"/api/admin/users/{target_id}/nuke",
        json={
            "password": password,
            "confirmPassword": password,
            "confirmationPhrase": admin_router.CONFIRMATION_PHRASE_USER_NUKE,
            "olderThanMonths": 6,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["deletedCount"] == 2

    remaining = await db.documents.find({"userId": target_id}).to_list(length=None)
    assert [d["invoiceNo"] for d in remaining] == ["RECENT"]


async def test_nuke_user_year_month_deletes_only_that_month(
    db: AsyncIOMotorDatabase, client: TestClient, admin_actor: tuple[ObjectId, str], _cleanup: list
) -> None:
    _admin_id, password = admin_actor
    target = await db.users.insert_one(_seed_user())
    target_id = target.inserted_id
    _cleanup.append(target_id)
    await db.documents.insert_many(
        [
            _seed_doc(target_id, createdAt=datetime(2025, 6, 15, tzinfo=UTC), invoiceNo="JUNE"),
            _seed_doc(
                target_id,
                createdAt=datetime(2025, 6, 30, 23, 59, tzinfo=UTC),
                invoiceNo="JUNE-LATE",
            ),
            _seed_doc(target_id, createdAt=datetime(2025, 7, 15, tzinfo=UTC), invoiceNo="JULY"),
        ]
    )

    resp = client.post(
        f"/api/admin/users/{target_id}/nuke",
        json={
            "password": password,
            "confirmPassword": password,
            "confirmationPhrase": admin_router.CONFIRMATION_PHRASE_USER_NUKE,
            "year": 2025,
            "month": 6,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["deletedCount"] == 2

    remaining = await db.documents.find({"userId": target_id}).to_list(length=None)
    assert [d["invoiceNo"] for d in remaining] == ["JULY"]


async def test_nuke_user_year_month_handles_december_year_boundary(
    db: AsyncIOMotorDatabase, client: TestClient, admin_actor: tuple[ObjectId, str], _cleanup: list
) -> None:
    _admin_id, password = admin_actor
    target = await db.users.insert_one(_seed_user())
    target_id = target.inserted_id
    _cleanup.append(target_id)
    await db.documents.insert_many(
        [
            _seed_doc(
                target_id, createdAt=datetime(2025, 12, 31, 23, 59, tzinfo=UTC), invoiceNo="DEC"
            ),
            _seed_doc(
                target_id, createdAt=datetime(2026, 1, 1, 0, 0, tzinfo=UTC), invoiceNo="JAN-NEXT"
            ),
        ]
    )

    resp = client.post(
        f"/api/admin/users/{target_id}/nuke",
        json={
            "password": password,
            "confirmPassword": password,
            "confirmationPhrase": admin_router.CONFIRMATION_PHRASE_USER_NUKE,
            "year": 2025,
            "month": 12,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["deletedCount"] == 1

    remaining = await db.documents.find({"userId": target_id}).to_list(length=None)
    assert [d["invoiceNo"] for d in remaining] == ["JAN-NEXT"]


# --- Global nuke: age-based and Year+Month, spans multiple users - uses year=2000 exclusively
# so it can NEVER match real application data (see module safety note above). ------------------


async def test_nuke_global_spans_multiple_users(
    db: AsyncIOMotorDatabase, client: TestClient, admin_actor: tuple[ObjectId, str], _cleanup: list
) -> None:
    _admin_id, password = admin_actor
    user_a = await db.users.insert_one(_seed_user())
    user_b = await db.users.insert_one(_seed_user())
    _cleanup.extend([user_a.inserted_id, user_b.inserted_id])
    old = datetime(_SAFE_PAST_YEAR, 3, 1, tzinfo=UTC)
    await db.documents.insert_many(
        [
            _seed_doc(user_a.inserted_id, createdAt=old, invoiceNo="A-OLD"),
            _seed_doc(user_b.inserted_id, createdAt=old, invoiceNo="B-OLD"),
        ]
    )

    resp = client.post(
        "/api/admin/nuke-global",
        json={
            "password": password,
            "confirmPassword": password,
            "confirmationPhrase": admin_router.CONFIRMATION_PHRASE_GLOBAL_NUKE,
            "year": _SAFE_PAST_YEAR,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["deletedCount"] == 2

    assert await db.documents.count_documents({"userId": user_a.inserted_id}) == 0
    assert await db.documents.count_documents({"userId": user_b.inserted_id}) == 0


async def test_nuke_global_year_month_spans_multiple_users_and_excludes_other_months(
    db: AsyncIOMotorDatabase, client: TestClient, admin_actor: tuple[ObjectId, str], _cleanup: list
) -> None:
    _admin_id, password = admin_actor
    user_a = await db.users.insert_one(_seed_user())
    user_b = await db.users.insert_one(_seed_user())
    _cleanup.extend([user_a.inserted_id, user_b.inserted_id])
    await db.documents.insert_many(
        [
            _seed_doc(
                user_a.inserted_id,
                createdAt=datetime(_SAFE_PAST_YEAR, 3, 10, tzinfo=UTC),
                invoiceNo="A-MARCH",
            ),
            _seed_doc(
                user_b.inserted_id,
                createdAt=datetime(_SAFE_PAST_YEAR, 3, 20, tzinfo=UTC),
                invoiceNo="B-MARCH",
            ),
            _seed_doc(
                user_a.inserted_id,
                createdAt=datetime(_SAFE_PAST_YEAR, 4, 1, tzinfo=UTC),
                invoiceNo="A-APRIL",
            ),
        ]
    )

    resp = client.post(
        "/api/admin/nuke-global",
        json={
            "password": password,
            "confirmPassword": password,
            "confirmationPhrase": admin_router.CONFIRMATION_PHRASE_GLOBAL_NUKE,
            "year": _SAFE_PAST_YEAR,
            "month": 3,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["deletedCount"] == 2

    remaining = await db.documents.find(
        {"userId": {"$in": [user_a.inserted_id, user_b.inserted_id]}}
    ).to_list(length=None)
    assert [d["invoiceNo"] for d in remaining] == ["A-APRIL"]


# --- Validation / safety-net behavior --------------------------------------------------------


async def test_nuke_password_mismatch_rejected(
    client: TestClient, admin_actor: tuple[ObjectId, str]
) -> None:
    _admin_id, password = admin_actor
    resp = client.post(
        "/api/admin/nuke-global",
        json={
            "password": password,
            "confirmPassword": "a-completely-different-password",
            "confirmationPhrase": admin_router.CONFIRMATION_PHRASE_GLOBAL_NUKE,
            "year": _SAFE_PAST_YEAR,
        },
    )
    assert resp.status_code == 400
    assert "match" in resp.json()["detail"].lower()


async def test_nuke_bad_confirmation_phrase_rejected(
    client: TestClient, admin_actor: tuple[ObjectId, str]
) -> None:
    _admin_id, password = admin_actor
    resp = client.post(
        "/api/admin/nuke-global",
        json={
            "password": password,
            "confirmPassword": password,
            "confirmationPhrase": "not the right phrase",
            "year": _SAFE_PAST_YEAR,
        },
    )
    assert resp.status_code == 400


async def test_nuke_global_non_admin_gets_403(client: TestClient) -> None:
    non_admin_id = ObjectId()

    def _fake_non_admin() -> CurrentUser:
        return CurrentUser(
            id=non_admin_id,
            username="notadmin2",
            email="notadmin2@example.invalid",
            role="user",
            token_version=0,
        )

    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = _fake_non_admin
    try:
        resp = client.post(
            "/api/admin/nuke-global",
            json={
                "password": "x",
                "confirmPassword": "x",
                "confirmationPhrase": admin_router.CONFIRMATION_PHRASE_GLOBAL_NUKE,
                "year": _SAFE_PAST_YEAR,
            },
        )
    finally:
        if previous is not None:
            app.dependency_overrides[get_current_user] = previous
        else:
            app.dependency_overrides.pop(get_current_user, None)
    assert resp.status_code == 403


async def test_nuke_user_non_admin_gets_403(client: TestClient) -> None:
    non_admin_id = ObjectId()

    def _fake_non_admin() -> CurrentUser:
        return CurrentUser(
            id=non_admin_id,
            username="notadmin3",
            email="notadmin3@example.invalid",
            role="user",
            token_version=0,
        )

    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = _fake_non_admin
    try:
        resp = client.post(
            f"/api/admin/users/{ObjectId()}/nuke",
            json={
                "password": "x",
                "confirmPassword": "x",
                "confirmationPhrase": admin_router.CONFIRMATION_PHRASE_USER_NUKE,
                "year": _SAFE_PAST_YEAR,
            },
        )
    finally:
        if previous is not None:
            app.dependency_overrides[get_current_user] = previous
        else:
            app.dependency_overrides.pop(get_current_user, None)
    assert resp.status_code == 403


# --- Rate limiting: 5 attempts / 24h per admin, shared across all nuke variants ---------------


async def test_nuke_rate_limit_blocks_sixth_attempt_in_24h(
    client: TestClient, admin_actor: tuple[ObjectId, str]
) -> None:
    _admin_id, password = admin_actor
    body = {
        "password": password,
        "confirmPassword": password,
        "confirmationPhrase": "deliberately wrong",  # cheap: rejected before any deletion logic
        "year": _SAFE_PAST_YEAR,
    }
    for _ in range(5):
        resp = client.post("/api/admin/nuke-global", json=body)
        assert resp.status_code == 400  # bad phrase, but still counts toward the rate limit

    resp = client.post("/api/admin/nuke-global", json=body)
    assert resp.status_code == 429


async def test_nuke_rate_limit_ignores_attempts_older_than_24h(
    db: AsyncIOMotorDatabase, client: TestClient, admin_actor: tuple[ObjectId, str]
) -> None:
    admin_id, password = admin_actor
    stale_time = datetime.now(UTC) - timedelta(hours=25)
    await db.auditlogs.insert_many(
        [
            {
                "userId": admin_id,
                "action": admin_router.NUKE_ATTEMPT_ACTION,
                "context": {},
                "createdAt": stale_time,
            }
            for _ in range(5)
        ]
    )

    resp = client.post(
        "/api/admin/nuke-global",
        json={
            "password": password,
            "confirmPassword": password,
            "confirmationPhrase": "deliberately wrong",
            "year": _SAFE_PAST_YEAR,
        },
    )
    # Rejected for the bad phrase, NOT 429 - proves entries older than the 24h window don't count.
    assert resp.status_code == 400


# --- Old user-facing nuke routes are gone -----------------------------------------------------


def test_old_purge_range_preview_route_is_gone(client: TestClient) -> None:
    # Two path segments - no route (single-segment {document_id}) can shadow this, so it's a
    # genuine 404 rather than falling through to a document-id lookup.
    resp = client.get("/api/documents/purge-range/preview")
    assert resp.status_code == 404


def test_old_purge_all_route_falls_through_to_invalid_document_id(
    client: TestClient, admin_actor: tuple[ObjectId, str]
) -> None:
    # Single path segment - DELETE /{document_id} still exists (that's the ordinary per-doc
    # delete route, on get_current_user not require_admin - admin_actor's override works fine
    # here purely to get past authentication), so "purge-all" now correctly reads as an invalid
    # document id (400) rather than matching the old dedicated nuke handler, which no longer
    # exists. This is the honest behavior given the route shape, and still proves the old
    # handler is gone: the response is the generic "Invalid document id" the catch-all
    # produces, not a nuke result.
    resp = client.delete("/api/documents/purge-all")
    assert resp.status_code == 400
    assert "invalid document id" in resp.json()["detail"].lower()


def test_old_purge_range_route_falls_through_to_invalid_document_id(
    client: TestClient, admin_actor: tuple[ObjectId, str]
) -> None:
    resp = client.delete("/api/documents/purge-range")
    assert resp.status_code == 400
    assert "invalid document id" in resp.json()["detail"].lower()
