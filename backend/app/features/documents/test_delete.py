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

# Real dev Mongo per .env, same isolation pattern as test_router.py: a randomly generated
# per-test-run userId, every seeded document cleaned up unconditionally.

_TEST_USER_ID = ObjectId()
_OTHER_USER_ID = ObjectId()


def _fake_current_user() -> CurrentUser:
    return CurrentUser(
        id=_TEST_USER_ID,
        username="delete-test-user",
        email="delete-test-user@example.invalid",
        role="user",
        token_version=0,
    )


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_current_user] = _fake_current_user
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
async def _cleanup(db: AsyncIOMotorDatabase) -> AsyncIterator[None]:
    yield
    await db.documents.delete_many({"userId": {"$in": [_TEST_USER_ID, _OTHER_USER_ID]}})
    await db.corrections.delete_many({"userId": _TEST_USER_ID})
    await db.orphanedfiles.delete_many({"userId": {"$in": [_TEST_USER_ID, _OTHER_USER_ID]}})


def _seed(**overrides: object) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "userId": _TEST_USER_ID,
        "uploadStatus": "processed",
        "createdAt": datetime.now(UTC),
        "invoiceNo": "DELETE-TEST",
    }
    doc.update(overrides)
    return doc


async def test_delete_permanently_removes_the_document_record(
    db: AsyncIOMotorDatabase, client: TestClient
) -> None:
    result = await db.documents.insert_one(_seed())
    doc_id = result.inserted_id

    resp = client.delete(f"/api/documents/{doc_id}")
    assert resp.status_code == 200
    assert "permanent" in resp.json()["message"].lower()

    assert await db.documents.find_one({"_id": doc_id}) is None

    get_resp = client.get(f"/api/documents/{doc_id}")
    assert get_resp.status_code == 404


async def test_delete_cascades_to_corrections(db: AsyncIOMotorDatabase, client: TestClient) -> None:
    result = await db.documents.insert_one(_seed())
    doc_id = result.inserted_id
    await db.corrections.insert_one(
        {
            "documentId": doc_id,
            "userId": _TEST_USER_ID,
            "field": "invoiceNo",
            "oldValue": "OLD",
            "newValue": "NEW",
            "createdAt": datetime.now(UTC),
        }
    )

    resp = client.delete(f"/api/documents/{doc_id}")
    assert resp.status_code == 200
    assert await db.corrections.count_documents({"documentId": doc_id}) == 0


async def test_delete_never_exported_document_is_fully_removed(
    db: AsyncIOMotorDatabase, client: TestClient
) -> None:
    # "Never exported" - this project has no export/download-tracking flag equivalent to the
    # sister project's exported-row tracking, so a document that has never been downloaded is
    # the closest analog; confirms full removal at the DB level regardless of that state.
    result = await db.documents.insert_one(_seed(part1FilePurged=False, part2FilePurged=False))
    doc_id = result.inserted_id

    resp = client.delete(f"/api/documents/{doc_id}")
    assert resp.status_code == 200
    assert await db.documents.count_documents({"_id": doc_id}) == 0


async def test_delete_preserves_audit_log_history(
    db: AsyncIOMotorDatabase, client: TestClient
) -> None:
    # Audit trail independence: the log entry recording the deletion itself must survive the
    # deletion - it's evidence of the action, not document state, and isn't cascade-deleted.
    result = await db.documents.insert_one(_seed())
    doc_id = result.inserted_id

    resp = client.delete(f"/api/documents/{doc_id}")
    assert resp.status_code == 200

    log_entry = await db.auditlogs.find_one(
        {"userId": _TEST_USER_ID, "action": "document_deleted", "context.documentId": str(doc_id)}
    )
    assert log_entry is not None
    await db.auditlogs.delete_one({"_id": log_entry["_id"]})  # not covered by the module cleanup


async def test_delete_preserves_orphan_record_independent_of_document_lifecycle(
    db: AsyncIOMotorDatabase, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Feature 3's admin cleanup page needs to retry/dismiss an orphaned file even after its
    # parent document is long gone - confirm deleting the document does NOT cascade-delete the
    # orphaned_files record for its (still-undeleted) file.
    import app.features.documents.router as documents_router

    fake_file_id = ObjectId()

    async def _always_fail(file_id: ObjectId) -> None:
        raise RuntimeError("simulated GridFS outage")

    monkeypatch.setattr(documents_router, "delete_file", _always_fail)

    result = await db.documents.insert_one(_seed(part1GridFsFileId=fake_file_id))
    doc_id = result.inserted_id

    resp = client.delete(f"/api/documents/{doc_id}")
    assert resp.status_code == 200
    assert await db.documents.find_one({"_id": doc_id}) is None

    orphan = await db.orphanedfiles.find_one({"fileId": fake_file_id})
    assert orphan is not None
    assert orphan["documentId"] == doc_id


async def test_delete_is_isolated_to_the_owning_user(
    db: AsyncIOMotorDatabase, client: TestClient
) -> None:
    other_users_doc = await db.documents.insert_one(_seed(userId=_OTHER_USER_ID))
    doc_id = other_users_doc.inserted_id

    resp = client.delete(f"/api/documents/{doc_id}")
    assert resp.status_code == 404

    assert await db.documents.find_one({"_id": doc_id}) is not None


async def test_delete_nonexistent_document_returns_404(client: TestClient) -> None:
    resp = client.delete(f"/api/documents/{ObjectId()}")
    assert resp.status_code == 404


async def test_delete_malformed_id_returns_400(client: TestClient) -> None:
    resp = client.delete("/api/documents/not-a-valid-object-id")
    assert resp.status_code == 400
