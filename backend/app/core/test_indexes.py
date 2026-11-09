"""Index setup: every index the app relies on exists after `_ensure_indexes`, twice in a row
(idempotent), and the unique ones really are unique. Runs on the in-process fake / *_test DB."""

from typing import Any

import pytest

from app.core.database import _ensure_indexes
from testkit import current_db

# collection -> (keys, unique) pairs the app depends on (derived from database.py).
EXPECTED: dict[str, list[tuple[list[tuple[str, int]], bool]]] = {
    "users": [([("email", 1)], True)],
    "documents": [
        ([("userId", 1), ("createdAt", -1)], False),
        ([("createdAt", 1)], False),  # admin telemetry
        ([("processedAt", 1)], False),  # admin telemetry
        ([("userId", 1), ("invoiceNo", 1)], False),
        ([("userId", 1), ("consigneeCode", 1)], False),
    ],
    "corrections": [([("documentId", 1)], False)],
    "auditlogs": [
        ([("userId", 1), ("createdAt", -1), ("_id", -1)], False),
        ([("action", 1)], False),
    ],
    "orphanedfiles": [([("fileId", 1)], True)],
    "chatmessages": [
        ([("threadUserId", 1), ("updatedAt", 1)], False),
        ([("threadUserId", 1), ("createdAt", 1)], False),
        ([("toAdminId", 1), ("readAt", 1)], False),
    ],
    "chatattachments": [
        ([("messageId", 1)], False),
        ([("threadUserId", 1)], False),
        ([("expired", 1), ("expiresAt", 1)], False),
    ],
    "chatfileorphans": [([("storedFileId", 1)], True)],
    "passwordresetrequests": [([("userId", 1)], True), ([("createdAt", -1)], False)],
}


async def _indexes(coll: Any) -> list[tuple[list[tuple[str, int]], bool]]:
    info = await coll.index_information()
    return [([(k, int(v)) for k, v in ix["key"]], bool(ix.get("unique"))) for ix in info.values()]


@pytest.mark.parametrize("collection", sorted(EXPECTED))
async def test_expected_indexes_exist_and_setup_is_idempotent(collection: str) -> None:
    db = current_db()
    await _ensure_indexes(db)
    await _ensure_indexes(db)  # second run: no error, nothing duplicated
    have = await _indexes(db[collection])
    for expected in EXPECTED[collection]:
        assert expected in have, f"{collection}: missing index {expected}"


async def test_stale_indexes_are_dropped() -> None:
    db = current_db()
    await db.documents.create_index([("userId", 1), ("isDeleted", 1), ("createdAt", -1)])
    await db.auditlogs.create_index([("userId", 1), ("createdAt", -1)])
    await _ensure_indexes(db)
    assert "userId_1_isDeleted_1_createdAt_-1" not in await db.documents.index_information()
    assert "userId_1_createdAt_-1" not in await db.auditlogs.index_information()


async def test_users_email_is_unique() -> None:
    db = current_db()
    await _ensure_indexes(db)
    await db.users.insert_one({"email": "a@example.com"})
    with pytest.raises(Exception):  # noqa: B017 - DuplicateKeyError (real) or the fake's twin
        await db.users.insert_one({"email": "a@example.com"})


async def test_only_one_open_password_reset_request_per_user() -> None:
    db = current_db()
    await _ensure_indexes(db)
    await db.passwordresetrequests.insert_one({"userId": "u1", "status": "open"})
    await db.passwordresetrequests.insert_one({"userId": "u1", "status": "closed"})
    await db.passwordresetrequests.insert_one({"userId": "u1", "status": "closed"})
    with pytest.raises(Exception):  # noqa: B017
        await db.passwordresetrequests.insert_one({"userId": "u1", "status": "open"})
