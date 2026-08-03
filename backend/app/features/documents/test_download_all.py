import io
import zipfile
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorGridFSBucket

from app.core.config import settings
from app.features.auth.dependencies import CurrentUser, get_current_user
from app.main import app

# Same real-dev-Mongo, per-test-run-unique-userId isolation pattern as test_router.py /
# test_delete.py: nothing here can touch a real user's data, and every seeded document +
# uploaded GridFS file is cleaned up unconditionally.
#
# GridFS files are uploaded through a GridFSBucket built on the *test's own* Motor client
# (the `db` fixture) rather than app.features.documents.gridfs_service.upload_buffer, which
# is bound to the app's lifespan-managed connection on TestClient's internal event loop -
# calling that directly from an async test function (a different event loop) raises "Future
# attached to a different loop", the same hazard documented in test_router.py's `db` fixture.
# GridFS content itself isn't loop-bound (it's just data in the DB), so uploading via a
# same-loop bucket and later reading it back through the app's own connection is safe.

_TEST_USER_ID = ObjectId()
_OTHER_USER_ID = ObjectId()
_uploaded_file_ids: list[ObjectId] = []


def _fake_current_user() -> CurrentUser:
    return CurrentUser(
        id=_TEST_USER_ID,
        username="download-all-test-user",
        email="download-all-test-user@example.invalid",
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
    bucket = AsyncIOMotorGridFSBucket(db)
    for file_id in _uploaded_file_ids:
        try:
            await bucket.delete(file_id)
        except Exception:  # noqa: BLE001 - best-effort test cleanup
            pass
    _uploaded_file_ids.clear()


async def _upload_test_file(db: AsyncIOMotorDatabase, filename: str, data: bytes) -> ObjectId:
    bucket = AsyncIOMotorGridFSBucket(db)
    file_id = await bucket.upload_from_stream(filename, data)
    _uploaded_file_ids.append(file_id)
    return file_id


async def _seed_with_files(
    db: AsyncIOMotorDatabase, invoice_no: str, **overrides: object
) -> dict[str, Any]:
    part1_id = await _upload_test_file(db, "part1.jpg", b"part1-bytes")
    part2_id = await _upload_test_file(db, "part2.jpg", b"part2-bytes")
    doc: dict[str, Any] = {
        "userId": _TEST_USER_ID,
        "uploadStatus": "processed",
        "createdAt": datetime.now(UTC),
        "invoiceNo": invoice_no,
        "part1GridFsFileId": part1_id,
        "part1OriginalFilename": "part1.jpg",
        "part1FilePurged": False,
        "part2GridFsFileId": part2_id,
        "part2OriginalFilename": "part2.jpg",
        "part2FilePurged": False,
    }
    doc.update(overrides)
    return doc


async def test_download_all_zips_every_doc_on_the_page(
    db: AsyncIOMotorDatabase, client: TestClient
) -> None:
    docs = [
        await _seed_with_files(db, "ZIP-A"),
        await _seed_with_files(db, "ZIP-B"),
    ]
    await db.documents.insert_many(docs)

    resp = client.post("/api/documents/download-all")
    assert resp.status_code == 200
    assert resp.headers["X-Included-Count"] == "2"
    assert resp.headers["X-Skipped-Count"] == "0"

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = set(zf.namelist())
    assert "ZIP-A/part1_part1.jpg" in names
    assert "ZIP-A/part2_part2.jpg" in names
    assert "ZIP-B/part1_part1.jpg" in names
    assert "ZIP-B/part2_part2.jpg" in names


async def test_download_all_skips_docs_with_purged_files(
    db: AsyncIOMotorDatabase, client: TestClient
) -> None:
    good = await _seed_with_files(db, "GOOD-DOC")
    purged = await _seed_with_files(db, "PURGED-DOC", part1FilePurged=True)
    await db.documents.insert_many([good, purged])

    resp = client.post("/api/documents/download-all")
    assert resp.status_code == 200
    assert resp.headers["X-Included-Count"] == "1"
    assert resp.headers["X-Skipped-Count"] == "1"

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = zf.namelist()
    assert any(n.startswith("GOOD-DOC/") for n in names)
    assert not any(n.startswith("PURGED-DOC/") for n in names)


async def test_download_all_every_file_purged_returns_zero_included_no_crash(
    db: AsyncIOMotorDatabase, client: TestClient
) -> None:
    doc = await _seed_with_files(db, "ALL-PURGED", part1FilePurged=True, part2FilePurged=True)
    await db.documents.insert_one(doc)

    resp = client.post("/api/documents/download-all")
    assert resp.status_code == 200
    assert resp.headers["X-Included-Count"] == "0"
    assert resp.headers["X-Skipped-Count"] == "1"
    # Still a structurally valid (empty) zip, not a broken/corrupt response.
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    assert zf.namelist() == []


async def test_download_all_skips_doc_when_gridfs_read_fails(
    db: AsyncIOMotorDatabase, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.features.documents.router as documents_router

    async def _always_fail(file_id: ObjectId) -> bytes:
        raise RuntimeError("simulated GridFS read failure")

    monkeypatch.setattr(documents_router, "download_buffer", _always_fail)

    doc = await _seed_with_files(db, "READ-FAILS")
    await db.documents.insert_one(doc)

    resp = client.post("/api/documents/download-all")
    assert resp.status_code == 200
    assert resp.headers["X-Included-Count"] == "0"
    assert resp.headers["X-Skipped-Count"] == "1"


async def test_download_all_respects_current_page_only(
    db: AsyncIOMotorDatabase, client: TestClient
) -> None:
    docs = [await _seed_with_files(db, f"PAGE-DOC-{i}") for i in range(3)]
    await db.documents.insert_many(docs)

    resp = client.post("/api/documents/download-all", params={"page": 1, "limit": 2})
    assert resp.status_code == 200
    assert resp.headers["X-Included-Count"] == "2"

    resp2 = client.post("/api/documents/download-all", params={"page": 2, "limit": 2})
    assert resp2.status_code == 200
    assert resp2.headers["X-Included-Count"] == "1"


async def test_download_all_is_isolated_to_the_owning_user(
    db: AsyncIOMotorDatabase, client: TestClient
) -> None:
    other_users_doc = await _seed_with_files(db, "OTHER-USER-DOC", userId=_OTHER_USER_ID)
    await db.documents.insert_one(other_users_doc)

    resp = client.post("/api/documents/download-all")
    assert resp.status_code == 200
    assert resp.headers["X-Included-Count"] == "0"

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    assert zf.namelist() == []
