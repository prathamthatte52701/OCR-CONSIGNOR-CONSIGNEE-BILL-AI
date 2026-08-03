"""Tracks GridFS delete failures for later admin retry/dismiss. Purely additive - callers
call this after catching a delete failure and must not let it change their own control flow."""

from datetime import UTC, datetime

from bson import ObjectId

from app.core.database import get_database


async def record_orphan(
    file_id: ObjectId, document_id: ObjectId | None, user_id: ObjectId | None, error: Exception
) -> None:
    db = get_database()
    now = datetime.now(UTC)
    await db.orphanedfiles.update_one(
        {"fileId": file_id},
        {
            "$set": {
                "documentId": document_id,
                "userId": user_id,
                "lastError": f"{type(error).__name__}: {error}",
                "lastAttemptAt": now,
            },
            "$setOnInsert": {"createdAt": now},
            "$inc": {"attemptCount": 1},
        },
        upsert=True,
    )
