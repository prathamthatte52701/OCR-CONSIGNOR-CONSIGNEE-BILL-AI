"""Tests for the admin orphaned-files list/retry/dismiss routes (Feature 3). Same fixture
conventions as test_router.py in this directory: real dev Mongo per .env, a single shared
TestClient with get_current_user overridden to a fake admin, monkeypatching
admin_router.delete_file (the module-level import) to force success/failure deterministically."""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

import app.features.admin.router as admin_router
from app.core.config import settings
from app.features.auth.dependencies import CurrentUser, get_current_user
from app.main import app

_ADMIN_ID = ObjectId()


def _fake_admin() -> CurrentUser:
    return CurrentUser(
        id=_ADMIN_ID,
        username="orphroutetest",
        email="orphan-route-admin@example.invalid",
        role="admin",
        token_version=0,
    )


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_current_user] = _fake_admin
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
    file_ids: list[ObjectId] = []
    yield file_ids
    if file_ids:
        await db.orphanedfiles.delete_many({"fileId": {"$in": file_ids}})
    await db.auditlogs.delete_many({"userId": _ADMIN_ID})


def _seed_orphan(**overrides: object) -> dict[str, Any]:
    now = datetime.now(UTC)
    doc: dict[str, Any] = {
        "fileId": ObjectId(),
        "documentId": ObjectId(),
        "userId": ObjectId(),
        "lastError": "RuntimeError: seeded failure",
        "lastAttemptAt": now,
        "createdAt": now,
        "attemptCount": 1,
    }
    doc.update(overrides)
    return doc


# --- GET /orphaned-files: pagination -----------------------------------------------------------


async def test_list_orphaned_files_paginated_sorted_by_last_attempt_desc(
    db: AsyncIOMotorDatabase, client: TestClient, _cleanup: list[ObjectId]
) -> None:
    now = datetime.now(UTC)
    records = [
        _seed_orphan(lastAttemptAt=now - timedelta(minutes=i), lastError=f"err-{i}")
        for i in range(3)
    ]
    _cleanup.extend(r["fileId"] for r in records)
    await db.orphanedfiles.insert_many(records)

    resp = client.get("/api/admin/orphaned-files", params={"page": 1, "limit": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 3
    assert body["page"] == 1
    assert body["limit"] == 2
    assert len(body["items"]) == 2
    # newest lastAttemptAt (err-0) sorts first among this test's own seeded rows.
    our_file_ids = {str(r["fileId"]) for r in records}
    ordered_ours = [item for item in body["items"] if item["fileId"] in our_file_ids]
    if len(ordered_ours) == 2:
        assert ordered_ours[0]["lastError"] == "err-0"

    item = body["items"][0]
    assert "id" in item and "fileId" in item and "documentId" in item and "userId" in item


# --- POST /orphaned-files/{id}/retry -------------------------------------------------------------


async def test_retry_success_removes_the_record(
    db: AsyncIOMotorDatabase, client: TestClient, monkeypatch: pytest.MonkeyPatch, _cleanup: list
) -> None:
    async def _succeed(file_id: ObjectId) -> None:
        return None

    monkeypatch.setattr(admin_router, "delete_file", _succeed)

    record = _seed_orphan()
    _cleanup.append(record["fileId"])
    result = await db.orphanedfiles.insert_one(record)

    resp = client.post(f"/api/admin/orphaned-files/{result.inserted_id}/retry")
    assert resp.status_code == 200
    assert "message" in resp.json()

    assert await db.orphanedfiles.find_one({"_id": result.inserted_id}) is None

    log = await db.auditlogs.find_one(
        {"userId": _ADMIN_ID, "action": "orphaned_file_retry_succeeded"}
    )
    assert log is not None


async def test_retry_failure_updates_record_in_place_not_duplicate_and_returns_error(
    db: AsyncIOMotorDatabase, client: TestClient, monkeypatch: pytest.MonkeyPatch, _cleanup: list
) -> None:
    async def _always_fail(file_id: ObjectId) -> None:
        raise RuntimeError("gridfs still unreachable")

    monkeypatch.setattr(admin_router, "delete_file", _always_fail)

    record = _seed_orphan(attemptCount=1, lastError="RuntimeError: original failure")
    _cleanup.append(record["fileId"])
    result = await db.orphanedfiles.insert_one(record)

    resp = client.post(f"/api/admin/orphaned-files/{result.inserted_id}/retry")
    assert resp.status_code == 500
    assert "gridfs still unreachable" in resp.json()["detail"]

    # Still exactly one record for this fileId, not a second one.
    count = await db.orphanedfiles.count_documents({"fileId": record["fileId"]})
    assert count == 1
    updated = await db.orphanedfiles.find_one({"fileId": record["fileId"]})
    assert updated is not None
    assert updated["attemptCount"] == 2
    assert "gridfs still unreachable" in updated["lastError"]

    log = await db.auditlogs.find_one({"userId": _ADMIN_ID, "action": "orphaned_file_retry_failed"})
    assert log is not None


async def test_retry_unknown_record_id_returns_404(client: TestClient) -> None:
    resp = client.post(f"/api/admin/orphaned-files/{ObjectId()}/retry")
    assert resp.status_code == 404


async def test_retry_malformed_record_id_returns_400(client: TestClient) -> None:
    resp = client.post("/api/admin/orphaned-files/not-an-object-id/retry")
    assert resp.status_code == 400


# --- DELETE /orphaned-files/{id}: dismiss ---------------------------------------------------------


async def test_dismiss_removes_record_without_retrying(
    db: AsyncIOMotorDatabase, client: TestClient, monkeypatch: pytest.MonkeyPatch, _cleanup: list
) -> None:
    called = False

    async def _should_not_be_called(file_id: ObjectId) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(admin_router, "delete_file", _should_not_be_called)

    record = _seed_orphan()
    _cleanup.append(record["fileId"])
    result = await db.orphanedfiles.insert_one(record)

    resp = client.delete(f"/api/admin/orphaned-files/{result.inserted_id}")
    assert resp.status_code == 200

    assert called is False  # dismiss never calls delete_file
    assert await db.orphanedfiles.find_one({"_id": result.inserted_id}) is None

    log = await db.auditlogs.find_one({"userId": _ADMIN_ID, "action": "orphaned_file_dismissed"})
    assert log is not None


async def test_dismiss_unknown_record_id_returns_404(client: TestClient) -> None:
    resp = client.delete(f"/api/admin/orphaned-files/{ObjectId()}")
    assert resp.status_code == 404


# --- Non-admin gets 403 on all three routes -------------------------------------------------------


def _override_non_admin() -> None:
    non_admin_id = ObjectId()

    def _fake_non_admin() -> CurrentUser:
        return CurrentUser(
            id=non_admin_id,
            username="notanadminx",
            email="notanadminx@example.invalid",
            role="user",
            token_version=0,
        )

    app.dependency_overrides[get_current_user] = _fake_non_admin


async def test_non_admin_gets_403_on_list_retry_and_dismiss(client: TestClient) -> None:
    previous_override = app.dependency_overrides[get_current_user]
    _override_non_admin()
    try:
        list_resp = client.get("/api/admin/orphaned-files")
        retry_resp = client.post(f"/api/admin/orphaned-files/{ObjectId()}/retry")
        dismiss_resp = client.delete(f"/api/admin/orphaned-files/{ObjectId()}")
    finally:
        app.dependency_overrides[get_current_user] = previous_override

    assert list_resp.status_code == 403
    assert retry_resp.status_code == 403
    assert dismiss_resp.status_code == 403
