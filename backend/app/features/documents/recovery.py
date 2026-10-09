"""Restart recovery for documents that were mid-processing when the server stopped.

The upload / reprocess routes mark a document "processing" and run the OCR pipeline as an
in-process background task. If the server restarts (deploy, crash, power cut) that task is lost
and the document would sit in "processing" forever. On startup this module re-queues those
documents - ONE AT A TIME, from the Part 1 / Part 2 files still stored in GridFS.

Restart-loop protection: a document that itself crashes the process (a pathological image that
takes OCR down) would otherwise be retried on every restart, forever. So every attempt is counted
in `recoveryAttempts` BEFORE processing starts (a hard crash still counts), and after
MAX_RECOVERY_ATTEMPTS the document is marked "failed" with a clear message instead of retried.

This runs as a background task (see main.lifespan) - it never blocks startup or /health."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from gridfs.errors import NoFile
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

MAX_RECOVERY_ATTEMPTS = 2

ATTEMPTS_EXHAUSTED_ERROR = (
    f"Processing was interrupted by a server restart {MAX_RECOVERY_ATTEMPTS} times in a row, so it "
    "was stopped to avoid a restart loop. Use Reprocess to try again."
)
FILES_MISSING_ERROR = (
    "Processing was interrupted by a server restart and the original file(s) are no longer "
    "stored, so it cannot be resumed. Please upload the document again."
)
PROCESSING_CRASHED_ERROR = "Processing could not be resumed after a server restart: {error}"

ProcessFn = Callable[..., Awaitable[None]]
ReadFileFn = Callable[[ObjectId], Awaitable[bytes]]

RECOVERY_FAILED_ACTION = "document_recovery_failed"
RECOVERY_REQUEUED_ACTION = "document_recovery_requeued"


async def _audit(
    db: AsyncIOMotorDatabase, doc: dict[str, Any], action: str, **context: Any
) -> None:
    # Same row shape as core.audit_log.log_action, written through the injected `db` handle.
    await db.auditlogs.insert_one(
        {
            "userId": doc.get("userId"),
            "action": action,
            "context": {"documentId": str(doc["_id"]), "recovery": True, **context},
            "createdAt": datetime.now(UTC),
        }
    )


async def _fail(db: AsyncIOMotorDatabase, doc: dict[str, Any], error: str, reason: str) -> None:
    await db.documents.update_one(
        {"_id": doc["_id"], "uploadStatus": "processing"},
        {
            "$set": {
                "uploadStatus": "failed",
                "processingError": error,
                "updatedAt": datetime.now(UTC),
            }
        },
    )
    await _audit(db, doc, RECOVERY_FAILED_ACTION, reason=reason)
    logger.warning("Recovery: document {} marked failed ({})", doc["_id"], reason)


async def recover_interrupted_documents(
    *,
    db: AsyncIOMotorDatabase | None = None,
    read_file: ReadFileFn | None = None,
    process: ProcessFn | None = None,
) -> dict[str, int]:
    """Re-queues every document stuck in "processing". Returns counts for logging/tests.

    The three keyword arguments are test seams (a loop-bound db handle, a GridFS reader, and a
    stand-in for the OCR pipeline); in production the app's own are used."""
    if db is None:
        from app.core.database import get_database

        db = get_database()
    if read_file is None:
        from app.features.documents.gridfs_service import download_buffer

        read_file = download_buffer
    if process is None:
        from app.features.documents.router import _run_pipeline_and_update

        process = _run_pipeline_and_update

    summary = {"found": 0, "requeued": 0, "failed_attempts": 0, "failed_missing_files": 0}
    stuck = (
        await db.documents.find({"uploadStatus": "processing"}).sort("createdAt", 1).to_list(None)
    )
    summary["found"] = len(stuck)

    for doc in stuck:  # strictly sequential: OCR is heavy, never run several at once
        attempts = int(doc.get("recoveryAttempts", 0))
        if attempts >= MAX_RECOVERY_ATTEMPTS:
            await _fail(db, doc, ATTEMPTS_EXHAUSTED_ERROR, "attempts exhausted")
            summary["failed_attempts"] += 1
            continue

        part1_id, part2_id = doc.get("part1GridFsFileId"), doc.get("part2GridFsFileId")
        if doc.get("part1FilePurged") or doc.get("part2FilePurged") or not part1_id or not part2_id:
            await _fail(db, doc, FILES_MISSING_ERROR, "stored files missing")
            summary["failed_missing_files"] += 1
            continue
        try:
            part1_bytes = await read_file(part1_id)
            part2_bytes = await read_file(part2_id)
        except NoFile:
            await _fail(db, doc, FILES_MISSING_ERROR, "stored files missing")
            summary["failed_missing_files"] += 1
            continue

        # Count the attempt BEFORE processing so a crash in the middle of it still counts.
        claimed = await db.documents.update_one(
            {"_id": doc["_id"], "uploadStatus": "processing"},
            {"$inc": {"recoveryAttempts": 1}, "$set": {"recoveryStartedAt": datetime.now(UTC)}},
        )
        if claimed.matched_count == 0:
            continue  # it finished (or was deleted) in the meantime
        await _audit(db, doc, RECOVERY_REQUEUED_ACTION, attempt=attempts + 1)

        try:
            await process(
                doc["_id"],
                part1_bytes,
                doc["part1MimeType"],
                part2_bytes,
                doc["part2MimeType"],
                is_reprocess=bool(doc.get("processedAt")),
            )
            summary["requeued"] += 1
        except Exception as exc:  # noqa: BLE001 - one bad document must not stop the others
            logger.exception("Recovery: processing document {} raised", doc["_id"])
            await _fail(db, doc, PROCESSING_CRASHED_ERROR.format(error=exc), "processing raised")
            summary["failed_attempts"] += 1

    if summary["found"]:
        logger.info("Restart recovery finished: {}", summary)
    return summary
