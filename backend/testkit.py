"""Small helpers shared by the test modules (users with real signed tokens, fake documents).
Everything here writes fake data into whatever database conftest.py selected - the in-process
fake or a *_test database - never a real one."""

import asyncio
import weakref
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket

from app.core.config import settings
from app.core.security import hash_password, sign_token

# A real Motor client is bound to the event loop it was created on. The app's own client lives
# on the TestClient's portal loop, while async tests run on pytest-asyncio's loop - so tests get
# their OWN client per loop (same database, same *_test name conftest enforced).
_clients: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, Any]" = weakref.WeakKeyDictionary()


def current_db() -> Any:
    loop = asyncio.get_running_loop()
    if loop not in _clients:
        _clients[loop] = AsyncIOMotorClient(settings.mongo_uri, tz_aware=True)
    return _clients[loop][settings.mongo_db_name]


PASSWORD = "Str0ng!Passw0rd"  # noqa: S105 - test-only value

PART1_BYTES = b"\xff\xd8\xffFAKE-PART1-JPEG-BYTES"
PART2_BYTES = b"\xff\xd8\xffFAKE-PART2-JPEG-BYTES"


async def make_user(
    role: str = "user", status: str | None = "approved", username: str | None = None
) -> dict[str, Any]:
    """Inserts a user (status None = legacy document without the field). The returned dict has
    `headers` holding a valid bearer token for the user's current tokenVersion."""
    uid = ObjectId()
    doc: dict[str, Any] = {
        "_id": uid,
        "username": username or f"u{str(uid)[-6:]}",
        "email": f"kit-{uid}@example.invalid",
        "passwordHash": hash_password(PASSWORD),
        "role": role,
        "tokenVersion": 0,
        "createdAt": datetime.now(UTC),
        "updatedAt": datetime.now(UTC),
    }
    if status is not None:
        doc["status"] = status
    await current_db().users.insert_one(doc)
    doc["id"] = str(uid)
    doc["headers"] = {"Authorization": f"Bearer {sign_token(str(uid), 0, role)}"}
    return doc


async def make_document(
    owner_id: ObjectId, *, with_files: bool = True, **fields: Any
) -> dict[str, Any]:
    """Inserts a processed document owned by `owner_id`, with tiny synthetic GridFS files."""
    doc: dict[str, Any] = {
        "userId": owner_id,
        "uploadStatus": "processed",
        "invoiceNo": f"INV-{ObjectId()}",
        "createdAt": datetime.now(UTC),
        "updatedAt": datetime.now(UTC),
        "lineItems": [],
        "part1OriginalFilename": "part1.jpg",
        "part1MimeType": "image/jpeg",
        "part1FilePurged": False,
        "part2OriginalFilename": "part2.jpg",
        "part2MimeType": "image/jpeg",
        "part2FilePurged": False,
    }
    if with_files:
        bucket = AsyncIOMotorGridFSBucket(current_db())
        doc["part1GridFsFileId"] = await bucket.upload_from_stream("part1.jpg", PART1_BYTES)
        doc["part2GridFsFileId"] = await bucket.upload_from_stream("part2.jpg", PART2_BYTES)
    doc.update(fields)
    result = await current_db().documents.insert_one(doc)
    doc["_id"] = result.inserted_id
    doc["id"] = str(result.inserted_id)
    return doc
