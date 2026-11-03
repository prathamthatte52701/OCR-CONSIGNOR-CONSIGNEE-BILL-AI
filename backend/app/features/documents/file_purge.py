"""File purge shared by the user routes (documents/router.py) and the admin routes
(admin/router.py), so the two can never drift apart. A failed delete never blocks: it is
recorded as an orphan and reported through the cleanup flag."""

from datetime import datetime
from typing import Any

from app.core.orphaned_files import record_orphan
from app.features.documents.gridfs_service import delete_file

PURGE_OK_MESSAGE = "Original files purged. Extracted data was preserved."
PURGE_FAILED_MESSAGE = (
    "The original files were removed from the document, but we couldn't fully clean up the "
    "stored data. This has been flagged for admin review - no action needed from you."
)
DELETE_OK_MESSAGE = "Document permanently deleted."
DELETE_FAILED_MESSAGE = (
    "Document permanently deleted, but we couldn't fully clean up its stored files. "
    "This has been flagged for admin review - no action needed from you."
)


async def best_effort_purge_files(doc: dict[str, Any]) -> bool:
    """Deletes both stored files; never raises. Returns True when any delete failed."""
    failed = False
    for key in ("part1GridFsFileId", "part2GridFsFileId"):
        file_id = doc.get(key)
        if file_id:
            try:
                await delete_file(file_id)
            except Exception as exc:  # noqa: BLE001 - best-effort, never blocks the delete
                failed = True
                await record_orphan(file_id, doc.get("_id"), doc.get("userId"), exc)
    return failed


async def purge_parts(doc: dict[str, Any], now: datetime) -> tuple[dict[str, Any], bool]:
    """Deletes the files of every part not yet purged and returns (updates, cleanup_failed).
    The updates ALWAYS mark each handled part purged and clear its dead file reference; the
    caller does the update_one, the audit entry and the message."""
    updates: dict[str, Any] = {}
    cleanup_failed = False
    for part in ("part1", "part2"):
        if doc.get(f"{part}FilePurged"):
            continue
        file_id = doc.get(f"{part}GridFsFileId")
        if file_id:
            try:
                await delete_file(file_id)
            except Exception as exc:  # noqa: BLE001 - tracked as an orphan, never blocks
                cleanup_failed = True
                await record_orphan(file_id, doc["_id"], doc.get("userId"), exc)
        updates[f"{part}FilePurged"] = True
        updates[f"{part}FilePurgedAt"] = now
        updates[f"{part}GridFsFileId"] = None
    return updates, cleanup_failed
