from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings
from app.features.auth.dependencies import CurrentUser, get_current_user
from app.main import app

# Real dev Mongo per .env, same pattern as documents/test_router.py: every seeded user/doc
# uses randomly generated ids so this can never touch real data, cleaned up unconditionally.

_ADMIN_ID = ObjectId()


def _fake_admin() -> CurrentUser:
    return CurrentUser(
        id=_ADMIN_ID,
        username="orphan-test-admin",
        email="orphan-test-admin@example.invalid",
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
    user_ids: list[ObjectId] = []
    yield user_ids
    if user_ids:
        await db.users.delete_many({"_id": {"$in": user_ids}})
        await db.documents.delete_many({"userId": {"$in": user_ids}})
        await db.corrections.delete_many({"userId": {"$in": user_ids}})
        await db.auditlogs.delete_many({"userId": {"$in": user_ids}})
        await db.orphanedfiles.delete_many({"userId": {"$in": user_ids}})


def _seed_user(**overrides: object) -> dict[str, Any]:
    now = datetime.now(UTC)
    doc = {
        "username": "orphtestusr",
        "email": f"orphan-target-{ObjectId()}@example.invalid",
        "passwordHash": "not-a-real-hash",
        "role": "user",
        "tokenVersion": 0,
        "createdAt": now,
        "updatedAt": now,
    }
    doc.update(overrides)
    return doc


def _seed_doc(user_id: ObjectId, **overrides: object) -> dict[str, Any]:
    now = datetime.now(UTC)
    doc = {
        "userId": user_id,
        "uploadStatus": "processed",
        "createdAt": now,
        "invoiceNo": "ADMIN-ORPHAN-TEST",
    }
    doc.update(overrides)
    return doc


async def test_admin_purge_files_endpoint_records_orphan_and_propagates_failure(
    db: AsyncIOMotorDatabase, client: TestClient, monkeypatch: pytest.MonkeyPatch, _cleanup: list
) -> None:
    import app.features.admin.router as admin_router

    async def _always_fail(file_id: ObjectId) -> None:
        raise RuntimeError("simulated GridFS outage (admin)")

    monkeypatch.setattr(admin_router, "delete_file", _always_fail)

    target_user = await db.users.insert_one(_seed_user())
    _cleanup.append(target_user.inserted_id)
    fake_file_id = ObjectId()
    result = await db.documents.insert_one(
        _seed_doc(target_user.inserted_id, part1GridFsFileId=fake_file_id, part1FilePurged=False)
    )
    doc_id = result.inserted_id

    resp = client.post(f"/api/admin/documents/{doc_id}/purge-files")
    assert resp.status_code == 500

    doc = await db.documents.find_one({"_id": doc_id})
    assert doc is not None
    assert doc.get("part1FilePurged") is not True

    orphan = await db.orphanedfiles.find_one({"fileId": fake_file_id})
    assert orphan is not None
    assert orphan["documentId"] == doc_id
    assert "simulated GridFS outage (admin)" in orphan["lastError"]


async def test_admin_delete_user_records_one_orphan_per_failing_file(
    db: AsyncIOMotorDatabase, client: TestClient, monkeypatch: pytest.MonkeyPatch, _cleanup: list
) -> None:
    import app.features.admin.router as admin_router

    async def _always_fail(file_id: ObjectId) -> None:
        raise RuntimeError("simulated GridFS outage during nuke")

    monkeypatch.setattr(admin_router, "delete_file", _always_fail)

    target_user = await db.users.insert_one(_seed_user())
    target_user_id = target_user.inserted_id
    _cleanup.append(target_user_id)

    file_ids = [ObjectId() for _ in range(4)]
    await db.documents.insert_many(
        [
            _seed_doc(target_user_id, part1GridFsFileId=file_ids[0], part2GridFsFileId=file_ids[1]),
            _seed_doc(target_user_id, part1GridFsFileId=file_ids[2], part2GridFsFileId=file_ids[3]),
        ]
    )

    resp = client.delete(f"/api/admin/users/{target_user_id}")
    assert resp.status_code == 200  # best-effort purge failures must never block user deletion

    remaining_docs = await db.documents.count_documents({"userId": target_user_id})
    assert remaining_docs == 0
    remaining_user = await db.users.find_one({"_id": target_user_id})
    assert remaining_user is None

    orphan_count = await db.orphanedfiles.count_documents({"fileId": {"$in": file_ids}})
    assert orphan_count == 4  # one record per failing file, not one per document or per call


async def test_admin_delete_document_permanently_removes_record_and_cascades_corrections(
    db: AsyncIOMotorDatabase, client: TestClient, _cleanup: list
) -> None:
    target_user = await db.users.insert_one(_seed_user())
    target_user_id = target_user.inserted_id
    _cleanup.append(target_user_id)
    result = await db.documents.insert_one(_seed_doc(target_user_id))
    doc_id = result.inserted_id
    await db.corrections.insert_one(
        {
            "documentId": doc_id,
            "userId": target_user_id,
            "field": "invoiceNo",
            "oldValue": "OLD",
            "newValue": "NEW",
            "createdAt": datetime.now(UTC),
        }
    )

    resp = client.delete(f"/api/admin/documents/{doc_id}")
    assert resp.status_code == 200
    assert "permanent" in resp.json()["message"].lower()

    assert await db.documents.find_one({"_id": doc_id}) is None
    assert await db.corrections.count_documents({"documentId": doc_id}) == 0

    get_resp = client.get(f"/api/admin/documents/{doc_id}")
    assert get_resp.status_code == 404


async def test_admin_non_admin_gets_403_on_purge_files(client: TestClient) -> None:
    non_admin_id = ObjectId()

    def _fake_non_admin() -> CurrentUser:
        return CurrentUser(
            id=non_admin_id,
            username="notanadmin",
            email="notanadmin@example.invalid",
            role="user",
            token_version=0,
        )

    # Swap the override in place rather than opening a second TestClient(app) context - that
    # would re-run the shared app's lifespan and tear down the global DB connection (a module-
    # level singleton in app.core.database) out from under every other test module in this run.
    previous_override = app.dependency_overrides[get_current_user]
    app.dependency_overrides[get_current_user] = _fake_non_admin
    try:
        resp = client.post(f"/api/admin/documents/{ObjectId()}/purge-files")
    finally:
        app.dependency_overrides[get_current_user] = previous_override
    assert resp.status_code == 403
