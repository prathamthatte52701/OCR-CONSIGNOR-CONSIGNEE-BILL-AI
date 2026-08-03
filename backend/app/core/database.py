"""Motor singleton connection + idempotent index creation. Never reconnect per-request."""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorGridFSBucket
from pymongo.errors import OperationFailure

from app.core.config import settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None
_gridfs: AsyncIOMotorGridFSBucket | None = None


async def connect_to_mongo() -> None:
    global _client, _db, _gridfs
    _client = AsyncIOMotorClient(settings.mongo_uri, tz_aware=True)
    _db = _client[settings.mongo_db_name]
    _gridfs = AsyncIOMotorGridFSBucket(_db)
    await _ensure_indexes(_db)


async def close_mongo_connection() -> None:
    global _client, _db, _gridfs
    if _client is not None:
        _client.close()
    _client = None
    _db = None
    _gridfs = None


def get_database() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Database not connected. Call connect_to_mongo() first.")
    return _db


def get_gridfs() -> AsyncIOMotorGridFSBucket:
    if _gridfs is None:
        raise RuntimeError("GridFS not connected. Call connect_to_mongo() first.")
    return _gridfs


async def _ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.users.create_index("email", unique=True)
    try:
        # Superseded by the userId+createdAt index below now that isDeleted no longer exists
        # on Document (soft-delete was removed) - drop the stale one if an earlier run created it.
        await db.documents.drop_index("userId_1_isDeleted_1_createdAt_-1")
    except OperationFailure:
        pass  # index never existed on this database - nothing to drop
    await db.documents.create_index([("userId", 1), ("createdAt", -1)])
    await db.documents.create_index([("userId", 1), ("invoiceNo", 1)])
    await db.documents.create_index([("userId", 1), ("consigneeCode", 1)])
    await db.corrections.create_index("documentId")
    await db.auditlogs.create_index([("userId", 1), ("createdAt", -1)])
    await db.auditlogs.create_index("action")
    await db.orphanedfiles.create_index("fileId", unique=True)
