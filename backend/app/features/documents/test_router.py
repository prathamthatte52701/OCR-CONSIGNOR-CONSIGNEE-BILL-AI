from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings
from app.features.auth.dependencies import CurrentUser, get_current_user
from app.features.documents.router import _upload_range_start_utc, ist_today_utc_range
from app.main import app

IST = ZoneInfo("Asia/Kolkata")


def test_ist_today_range_covers_midday_ist() -> None:
    # 2026-01-15 12:00 IST is well inside its own IST calendar day.
    now_ist = datetime(2026, 1, 15, 12, 0, tzinfo=IST)
    start, end = ist_today_utc_range(now_ist)
    assert start <= now_ist.astimezone(UTC) < end


def test_ist_today_range_is_exactly_24_hours() -> None:
    now_ist = datetime(2026, 1, 15, 9, 30, tzinfo=IST)
    start, end = ist_today_utc_range(now_ist)
    assert (end - start).total_seconds() == 24 * 3600


def test_ist_midnight_boundary_not_shared_with_previous_utc_day() -> None:
    # 00:30 IST on 2026-01-15 is 19:00 UTC on 2026-01-14 - a naive UTC-day query would
    # miss this instant entirely; the IST-aware range must still include it.
    now_ist = datetime(2026, 1, 15, 0, 30, tzinfo=IST)
    start, end = ist_today_utc_range(now_ist)
    instant_utc = now_ist.astimezone(UTC)
    assert start <= instant_utc < end
    assert instant_utc.date() == datetime(2026, 1, 14).date()  # confirms the UTC-day mismatch


# --- _upload_range_start_utc: pure boundary math, no DB needed ---------------------------


def test_range_today_start_is_midnight_utc_same_day() -> None:
    now = datetime(2026, 7, 31, 15, 42, 7, tzinfo=UTC)
    assert _upload_range_start_utc("today", now) == datetime(2026, 7, 31, 0, 0, 0, tzinfo=UTC)


def test_range_week_starts_monday_when_now_is_monday() -> None:
    # 2026-07-27 is a Monday - the week bucket should start at that same day's midnight.
    now = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)
    assert _upload_range_start_utc("week", now) == datetime(2026, 7, 27, 0, 0, tzinfo=UTC)


def test_range_week_starts_monday_when_now_is_sunday() -> None:
    # 2026-08-02 is a Sunday, the last day of the week starting 2026-07-27 (Monday).
    now = datetime(2026, 8, 2, 23, 59, tzinfo=UTC)
    assert _upload_range_start_utc("week", now) == datetime(2026, 7, 27, 0, 0, tzinfo=UTC)


def test_range_month_starts_first_of_month() -> None:
    now = datetime(2026, 7, 31, 23, 0, tzinfo=UTC)
    assert _upload_range_start_utc("month", now) == datetime(2026, 7, 1, 0, 0, tzinfo=UTC)


def test_range_year_starts_jan_1() -> None:
    now = datetime(2026, 7, 31, 23, 0, tzinfo=UTC)
    assert _upload_range_start_utc("year", now) == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


def test_range_unknown_key_raises() -> None:
    with pytest.raises(ValueError):
        _upload_range_start_utc("decade", datetime(2026, 7, 31, tzinfo=UTC))


# --- GET /api/documents?range=... wiring: integration tests against the real dev Mongo ---
# instance from .env. Every seeded document uses a randomly generated, single-test-run-unique
# userId so these tests can never read or mutate a real user's data, and every document
# inserted is deleted again in the autouse cleanup fixture below (best-effort, runs even if
# a test fails or raises).

_TEST_USER_ID = ObjectId()


def _fake_current_user() -> CurrentUser:
    return CurrentUser(
        id=_TEST_USER_ID,
        username="range-filter-test-user",
        email="range-filter-test-user@example.invalid",
        role="user",
        token_version=0,
    )


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_current_user] = _fake_current_user
    # raise_server_exceptions=False so an unhandled exception in a route surfaces as the real
    # 500 response a production ASGI server would return, instead of re-raising into the test
    # (the default, meant for debugging) - needed to test the orphan-tracking failure paths.
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
async def db() -> AsyncIterator[AsyncIOMotorDatabase]:
    # A fresh Motor client bound to *this* test's running event loop, deliberately separate
    # from the app's own lifespan-managed singleton (app.core.database), which lives on
    # TestClient's internal ASGI event loop - reusing that client from here raises "Future
    # attached to a different loop". Both point at the same real dev Mongo instance, so writes
    # made here are still visible to requests the `client` fixture sends through the app.
    test_client: AsyncIOMotorClient = AsyncIOMotorClient(settings.mongo_uri, tz_aware=True)
    try:
        yield test_client[settings.mongo_db_name]
    finally:
        test_client.close()


@pytest.fixture(autouse=True)
async def _cleanup_seeded_docs(db: AsyncIOMotorDatabase) -> AsyncIterator[None]:
    yield
    await db.documents.delete_many({"userId": _TEST_USER_ID})


def _seed(created_at: datetime, **overrides: object) -> dict[str, Any]:
    doc = {
        "userId": _TEST_USER_ID,
        "uploadStatus": "processed",
        "createdAt": created_at,
        "invoiceNo": "BASE-INV",
        "consigneeCode": "BASE-CODE",
    }
    doc.update(overrides)
    return doc


async def test_range_today_excludes_older_documents(
    db: AsyncIOMotorDatabase, client: TestClient
) -> None:
    now = datetime.now(UTC)
    await db.documents.insert_many(
        [
            _seed(now, invoiceNo="TODAY-1"),
            _seed(now - timedelta(days=1), invoiceNo="YESTERDAY"),
            _seed(now - timedelta(days=8), invoiceNo="WEEK-AGO"),
        ]
    )
    resp = client.get("/api/documents", params={"range": "today"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert [item["invoiceNo"] for item in body["items"]] == ["TODAY-1"]


async def test_range_year_zero_results_returns_empty_list(
    db: AsyncIOMotorDatabase, client: TestClient
) -> None:
    await db.documents.insert_one(_seed(datetime(2000, 6, 1, tzinfo=UTC), invoiceNo="OLD-2000"))
    resp = client.get("/api/documents", params={"range": "year"})
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"items": [], "total": 0, "page": 1, "limit": 30}


async def test_range_composes_with_pagination(db: AsyncIOMotorDatabase, client: TestClient) -> None:
    now = datetime.now(UTC)
    await db.documents.insert_many(
        [_seed(now - timedelta(seconds=i), invoiceNo=f"PAGE-{i}") for i in range(35)]
    )
    page1 = client.get("/api/documents", params={"range": "month", "page": 1, "limit": 30})
    page2 = client.get("/api/documents", params={"range": "month", "page": 2, "limit": 30})
    assert page1.json()["total"] == 35
    assert len(page1.json()["items"]) == 30
    assert page2.json()["total"] == 35
    assert len(page2.json()["items"]) == 5


async def test_invalid_range_value_returns_422(client: TestClient) -> None:
    resp = client.get("/api/documents", params={"range": "decade"})
    assert resp.status_code == 422


async def test_omitting_range_returns_unfiltered_list_unchanged(
    db: AsyncIOMotorDatabase, client: TestClient
) -> None:
    await db.documents.insert_many(
        [
            _seed(datetime.now(UTC), invoiceNo="RECENT"),
            _seed(datetime(2000, 1, 1, tzinfo=UTC), invoiceNo="ANCIENT"),
        ]
    )
    resp = client.get("/api/documents")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert {item["invoiceNo"] for item in body["items"]} == {"RECENT", "ANCIENT"}


async def test_range_composes_with_invoice_no_as_and_not_or(
    db: AsyncIOMotorDatabase, client: TestClient
) -> None:
    now = datetime.now(UTC)
    await db.documents.insert_many(
        [
            _seed(now, invoiceNo="MATCH-BOTH"),
            _seed(now, invoiceNo="OTHER-INVOICE"),  # matches range, not invoiceNo
            _seed(now - timedelta(days=400), invoiceNo="MATCH-BOTH"),  # matches invoiceNo only
        ]
    )
    resp = client.get("/api/documents", params={"range": "today", "invoiceNo": "MATCH-BOTH"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["invoiceNo"] == "MATCH-BOTH"


# --- GridFS orphan tracking (Feature 2): purge-files / delete keep their existing status-code
# behavior unchanged, orphan tracking is purely additive on top. ------------------------------


@pytest.fixture(autouse=True)
async def _cleanup_seeded_orphans(db: AsyncIOMotorDatabase) -> AsyncIterator[None]:
    yield
    await db.orphanedfiles.delete_many({"userId": _TEST_USER_ID})


async def test_purge_files_endpoint_records_orphan_and_propagates_failure(
    db: AsyncIOMotorDatabase, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.features.documents.router as documents_router

    fake_file_id = ObjectId()

    async def _always_fail(file_id: ObjectId) -> None:
        raise RuntimeError("simulated GridFS outage")

    monkeypatch.setattr(documents_router, "delete_file", _always_fail)

    result = await db.documents.insert_one(
        _seed(
            datetime.now(UTC),
            invoiceNo="PURGE-FAIL",
            part1GridFsFileId=fake_file_id,
            part1FilePurged=False,
        )
    )
    doc_id = result.inserted_id

    resp = client.post(f"/api/documents/{doc_id}/purge-files")
    assert resp.status_code == 500

    doc = await db.documents.find_one({"_id": doc_id})
    assert doc is not None
    assert doc.get("part1FilePurged") is not True  # failed delete must not be marked purged

    orphan = await db.orphanedfiles.find_one({"fileId": fake_file_id})
    assert orphan is not None
    assert orphan["documentId"] == doc_id
    assert orphan["userId"] == _TEST_USER_ID
    assert "simulated GridFS outage" in orphan["lastError"]


async def test_delete_endpoint_still_succeeds_when_gridfs_fails(
    db: AsyncIOMotorDatabase, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.features.documents.router as documents_router

    fake_file_id = ObjectId()

    async def _always_fail(file_id: ObjectId) -> None:
        raise RuntimeError("simulated GridFS outage")

    monkeypatch.setattr(documents_router, "delete_file", _always_fail)

    result = await db.documents.insert_one(
        _seed(datetime.now(UTC), invoiceNo="DELETE-FAIL", part1GridFsFileId=fake_file_id)
    )
    doc_id = result.inserted_id

    resp = client.delete(f"/api/documents/{doc_id}")
    assert resp.status_code == 200  # best-effort purge failure must never block the delete

    orphan = await db.orphanedfiles.find_one({"fileId": fake_file_id})
    assert orphan is not None
    assert orphan["documentId"] == doc_id


async def test_successful_deletion_creates_zero_orphan_records(
    db: AsyncIOMotorDatabase, client: TestClient
) -> None:
    # A file id that was never actually uploaded to GridFS - delete_file() swallows the
    # resulting NoFile internally (that's not a real failure, the file is already gone), so
    # no exception ever reaches _best_effort_purge_files and no orphan should be recorded.
    never_uploaded_file_id = ObjectId()
    result = await db.documents.insert_one(
        _seed(datetime.now(UTC), invoiceNo="CLEAN-DELETE", part1GridFsFileId=never_uploaded_file_id)
    )
    doc_id = result.inserted_id

    resp = client.delete(f"/api/documents/{doc_id}")
    assert resp.status_code == 200

    orphan = await db.orphanedfiles.find_one({"fileId": never_uploaded_file_id})
    assert orphan is None
