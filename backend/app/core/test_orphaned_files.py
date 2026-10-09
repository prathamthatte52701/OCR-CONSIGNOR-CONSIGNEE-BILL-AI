from collections.abc import Iterator

import pytest
from anyio.from_thread import BlockingPortal
from bson import ObjectId
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.database import Database

from app.core.config import settings
from app.core.orphaned_files import record_orphan
from app.main import app

# Real dev Mongo per .env (no mocks/fixtures in this codebase's test setup) - every record
# uses a randomly generated fileId so this test can never collide with real orphan data, and
# every record inserted is cleaned up in the autouse fixture below. record_orphan() reads
# app.core.database's connected singleton (bound to the TestClient's own event loop), so it
# must be invoked via _portal(client).call(...) rather than awaited directly from a pytest-
# asyncio test coroutine (that would run on a *different* loop and raise "attached to a
# different loop") - a sync pymongo client is used for the read-back assertions to sidestep
# the event-loop question entirely for those.


def _portal(test_client: TestClient) -> BlockingPortal:
    assert test_client.portal is not None  # set while the TestClient context manager is open
    return test_client.portal


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sync_db() -> Iterator[Database]:
    mongo: MongoClient = MongoClient(settings.mongo_uri, tz_aware=True)
    try:
        yield mongo[settings.mongo_db_name]
    finally:
        mongo.close()


@pytest.fixture(autouse=True)
def _cleanup(sync_db: Database) -> Iterator[list[ObjectId]]:
    file_ids: list[ObjectId] = []
    yield file_ids
    if file_ids:
        sync_db.orphanedfiles.delete_many({"fileId": {"$in": file_ids}})


def test_record_orphan_creates_one_record(
    client: TestClient, sync_db: Database, _cleanup: list[ObjectId]
) -> None:
    file_id, doc_id, user_id = ObjectId(), ObjectId(), ObjectId()
    _cleanup.append(file_id)
    _portal(client).call(
        record_orphan, file_id, doc_id, user_id, RuntimeError("gridfs unreachable")
    )

    record = sync_db.orphanedfiles.find_one({"fileId": file_id})
    assert record is not None
    assert record["documentId"] == doc_id
    assert record["userId"] == user_id
    assert "gridfs unreachable" in record["lastError"]
    assert record["attemptCount"] == 1


def test_record_orphan_repeated_failure_updates_not_duplicates(
    client: TestClient, sync_db: Database, _cleanup: list[ObjectId]
) -> None:
    file_id, doc_id, user_id = ObjectId(), ObjectId(), ObjectId()
    _cleanup.append(file_id)
    _portal(client).call(record_orphan, file_id, doc_id, user_id, RuntimeError("first failure"))
    _portal(client).call(record_orphan, file_id, doc_id, user_id, RuntimeError("second failure"))

    count = sync_db.orphanedfiles.count_documents({"fileId": file_id})
    assert count == 1
    record = sync_db.orphanedfiles.find_one({"fileId": file_id})
    assert record is not None
    assert record["attemptCount"] == 2
    assert "second failure" in record["lastError"]


def test_record_orphan_preserves_created_at_across_retries(
    client: TestClient, sync_db: Database, _cleanup: list[ObjectId]
) -> None:
    file_id, doc_id, user_id = ObjectId(), ObjectId(), ObjectId()
    _cleanup.append(file_id)
    _portal(client).call(record_orphan, file_id, doc_id, user_id, RuntimeError("first failure"))
    first = sync_db.orphanedfiles.find_one({"fileId": file_id})
    assert first is not None

    _portal(client).call(record_orphan, file_id, doc_id, user_id, RuntimeError("second failure"))
    second = sync_db.orphanedfiles.find_one({"fileId": file_id})
    assert second is not None
    assert second["createdAt"] == first["createdAt"]
    assert second["lastAttemptAt"] >= first["lastAttemptAt"]


def test_record_orphan_distinct_files_get_distinct_records(
    client: TestClient, sync_db: Database, _cleanup: list[ObjectId]
) -> None:
    file_id_a, file_id_b = ObjectId(), ObjectId()
    doc_id, user_id = ObjectId(), ObjectId()
    _cleanup.extend([file_id_a, file_id_b])
    _portal(client).call(record_orphan, file_id_a, doc_id, user_id, RuntimeError("failure a"))
    _portal(client).call(record_orphan, file_id_b, doc_id, user_id, RuntimeError("failure b"))

    count = sync_db.orphanedfiles.count_documents({"fileId": {"$in": [file_id_a, file_id_b]}})
    assert count == 2


def test_unique_index_on_file_id(client: TestClient, sync_db: Database) -> None:
    indexes = sync_db.orphanedfiles.index_information()
    assert "fileId_1" in indexes
    assert indexes["fileId_1"]["unique"] is True


if __name__ == "__main__":
    with TestClient(app) as c:
        mongo: MongoClient = MongoClient(settings.mongo_uri, tz_aware=True)
        d = mongo[settings.mongo_db_name]
        fid = ObjectId()
        _portal(c).call(record_orphan, fid, ObjectId(), ObjectId(), RuntimeError("demo failure"))
        rec = d.orphanedfiles.find_one({"fileId": fid})
        assert rec is not None and rec["attemptCount"] == 1
        _portal(c).call(record_orphan, fid, ObjectId(), ObjectId(), RuntimeError("demo failure 2"))
        rec2 = d.orphanedfiles.find_one({"fileId": fid})
        assert rec2 is not None and rec2["attemptCount"] == 2
        assert d.orphanedfiles.count_documents({"fileId": fid}) == 1
        d.orphanedfiles.delete_many({"fileId": fid})
        mongo.close()
        print("orphaned_files self-check passed")
