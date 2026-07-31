"""Document routes: dual-file upload, list/search, edit, reprocess, and the three delete
tiers (soft-delete, purge-files, purge-all/purge-range). Per-user data isolation on every
query - every filter includes userId, malformed ids return 400, other users' documents 404."""

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.audit_log import log_action
from app.core.database import get_database
from app.core.object_id import is_valid_object_id
from app.core.security import verify_password
from app.features.auth.dependencies import CurrentUser, get_current_user
from app.features.documents.correction_service import apply_field_correction
from app.features.documents.gridfs_service import delete_file, download_buffer, upload_buffer
from app.features.documents.processing import run_full_pipeline
from app.features.documents.schemas import (
    CorrectRequest,
    DocumentListResponse,
    PurgeAllRequest,
    PurgeRangeRequest,
    StatsResponse,
    UploadResponse,
)

IST = ZoneInfo("Asia/Kolkata")

router = APIRouter()

MAX_FILE_SIZE = 5 * 1024 * 1024
ALLOWED_MIME_TYPES = {"image/jpeg", "image/jpg", "image/png", "application/pdf"}
_MAGIC_BYTES: dict[bytes, str] = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"%PDF": "application/pdf",
}

CONFIRMATION_PHRASE_ALL = "DELETE"
CONFIRMATION_PHRASE_RANGE = "DELETE RANGE"


def _sniff_mime_type(data: bytes) -> str | None:
    for magic, mime in _MAGIC_BYTES.items():
        if data.startswith(magic):
            return mime
    return None


def _serialize_document(doc: dict[str, Any]) -> dict[str, Any]:
    result = dict(doc)
    result["id"] = str(result.pop("_id"))
    result.pop("userId", None)
    result.pop("part1GridFsFileId", None)
    result.pop("part2GridFsFileId", None)
    return result


async def _get_owned_document(
    db: AsyncIOMotorDatabase, document_id: str, user_id: ObjectId
) -> dict[str, Any]:
    if not is_valid_object_id(document_id):
        raise HTTPException(status_code=400, detail="Invalid document id.")
    doc = await db.documents.find_one(
        {"_id": ObjectId(document_id), "userId": user_id, "isDeleted": False}
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc


async def _best_effort_purge_files(doc: dict[str, Any]) -> None:
    for key in ("part1GridFsFileId", "part2GridFsFileId"):
        file_id = doc.get(key)
        if file_id:
            try:
                await delete_file(file_id)
            except Exception:  # noqa: BLE001 - best-effort, never blocks the delete
                pass


def _build_range_filter(
    user_id: ObjectId, older_than_months: int | None, year: int | None
) -> dict[str, Any]:
    if (older_than_months is None) == (year is None):
        raise HTTPException(
            status_code=400, detail="Provide exactly one of olderThanMonths or year."
        )
    query: dict[str, Any] = {"userId": user_id}
    if older_than_months is not None:
        if older_than_months not in (3, 6, 9):
            raise HTTPException(status_code=400, detail="olderThanMonths must be 3, 6, or 9.")
        cutoff = datetime.now(UTC) - timedelta(days=30 * older_than_months)
        query["createdAt"] = {"$lt": cutoff}
    else:
        assert year is not None  # guaranteed by the XOR check above
        start = datetime(year, 1, 1, tzinfo=UTC)
        end = datetime(year + 1, 1, 1, tzinfo=UTC)
        query["createdAt"] = {"$gte": start, "$lt": end}
    return query


async def _run_pipeline_and_update(
    doc_id: ObjectId,
    part1_bytes: bytes,
    part1_mime: str,
    part2_bytes: bytes,
    part2_mime: str,
    *,
    is_reprocess: bool,
) -> None:
    db = get_database()
    try:
        update = await run_full_pipeline(part1_bytes, part1_mime, part2_bytes, part2_mime)
        now = datetime.now(UTC)
        update["uploadStatus"] = "processed"
        update["processingError"] = None
        update["processedAt"] = now
        update["updatedAt"] = now
        if is_reprocess:
            update["reprocessedAt"] = now
            update["edited"] = False
        await db.documents.update_one({"_id": doc_id}, {"$set": update})
    except Exception as exc:  # noqa: BLE001 - pipeline failure must not crash the background task
        await db.documents.update_one(
            {"_id": doc_id},
            {
                "$set": {
                    "uploadStatus": "failed",
                    "processingError": (
                        f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
                    ),
                    "updatedAt": datetime.now(UTC),
                }
            },
        )


# --- Nuke-tier routes registered BEFORE /{document_id} so Starlette's path matching picks
# the literal route instead of trying (and failing) to parse "purge-all"/"purge-range" as
# an ObjectId. ---


@router.get("/purge-range/preview")
async def preview_purge_range(
    older_than_months: int | None = Query(None, alias="olderThanMonths"),
    year: int | None = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, int]:
    db = get_database()
    query = _build_range_filter(current_user.id, older_than_months, year)
    count = await db.documents.count_documents(query)
    return {"matchingCount": count}


@router.delete("/purge-range")
async def purge_range(
    body: PurgeRangeRequest, current_user: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    if body.confirmation_phrase != CONFIRMATION_PHRASE_RANGE:
        raise HTTPException(
            status_code=400, detail=f"Type '{CONFIRMATION_PHRASE_RANGE}' exactly to confirm."
        )
    db = get_database()
    user = await db.users.find_one({"_id": current_user.id})
    if user is None or not verify_password(body.password, user["passwordHash"]):
        await log_action(current_user.id, "purge_range_blocked", {"reason": "bad_password"})
        raise HTTPException(status_code=400, detail="Incorrect password.")

    query = _build_range_filter(current_user.id, body.older_than_months, body.year)
    docs = await db.documents.find(query).to_list(length=None)
    for doc in docs:
        await _best_effort_purge_files(doc)
    doc_ids = [doc["_id"] for doc in docs]
    result = await db.documents.delete_many(query)
    if doc_ids:
        await db.corrections.delete_many({"documentId": {"$in": doc_ids}})
    await log_action(current_user.id, "purge_range", {"deletedCount": result.deleted_count})
    return {
        "message": f"Deleted {result.deleted_count} documents.",
        "deletedCount": result.deleted_count,
    }


@router.delete("/purge-all")
async def purge_all(
    body: PurgeAllRequest, current_user: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    if body.confirmation_phrase != CONFIRMATION_PHRASE_ALL:
        raise HTTPException(
            status_code=400, detail=f"Type '{CONFIRMATION_PHRASE_ALL}' exactly to confirm."
        )
    db = get_database()
    user = await db.users.find_one({"_id": current_user.id})
    if user is None or not verify_password(body.password, user["passwordHash"]):
        await log_action(current_user.id, "purge_all_blocked", {"reason": "bad_password"})
        raise HTTPException(status_code=400, detail="Incorrect password.")

    docs = await db.documents.find({"userId": current_user.id}).to_list(length=None)
    for doc in docs:
        await _best_effort_purge_files(doc)
    result = await db.documents.delete_many({"userId": current_user.id})
    await db.corrections.delete_many({"userId": current_user.id})
    await log_action(current_user.id, "purge_all", {"deletedCount": result.deleted_count})
    return {
        "message": f"All data deleted ({result.deleted_count} documents).",
        "deletedCount": result.deleted_count,
    }


@router.post("/upload", status_code=201, response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    part1: UploadFile = File(...),
    part2: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> UploadResponse:
    part1_bytes = await part1.read()
    part2_bytes = await part2.read()

    for label, data in (("Part 1", part1_bytes), ("Part 2", part2_bytes)):
        if not data:
            raise HTTPException(status_code=400, detail=f"{label} file is empty.")
        if len(data) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"{label} file exceeds the 5MB limit.")

    part1_mime = _sniff_mime_type(part1_bytes)
    part2_mime = _sniff_mime_type(part2_bytes)
    if part1_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Part 1 file type not supported.")
    if part2_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Part 2 file type not supported.")

    db = get_database()
    part1_file_id = await upload_buffer(part1_bytes, part1.filename or "part1", part1_mime)
    part2_file_id = await upload_buffer(part2_bytes, part2.filename or "part2", part2_mime)

    now = datetime.now(UTC)
    result = await db.documents.insert_one(
        {
            "userId": current_user.id,
            "isDeleted": False,
            "uploadStatus": "processing",
            "edited": False,
            "hasLowConfidenceFields": False,
            "multiPage": False,
            "part1GridFsFileId": part1_file_id,
            "part1OriginalFilename": part1.filename,
            "part1MimeType": part1_mime,
            "part1Size": len(part1_bytes),
            "part1FilePurged": False,
            "part2GridFsFileId": part2_file_id,
            "part2OriginalFilename": part2.filename,
            "part2MimeType": part2_mime,
            "part2Size": len(part2_bytes),
            "part2FilePurged": False,
            "createdAt": now,
            "updatedAt": now,
        }
    )
    doc_id = result.inserted_id

    background_tasks.add_task(
        _run_pipeline_and_update,
        doc_id,
        part1_bytes,
        part1_mime,
        part2_bytes,
        part2_mime,
        is_reprocess=False,
    )
    await log_action(current_user.id, "document_uploaded", {"documentId": str(doc_id)})
    return UploadResponse(id=str(doc_id), upload_status="processing")


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    current_user: CurrentUser = Depends(get_current_user),
    invoice_no: str | None = Query(None, alias="invoiceNo"),
    consignee_code: str | None = Query(None, alias="consigneeCode"),
    date: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
) -> DocumentListResponse:
    db = get_database()
    query: dict[str, Any] = {"userId": current_user.id, "isDeleted": False}
    if invoice_no:
        query["invoiceNo"] = {"$regex": re.escape(invoice_no), "$options": "i"}
    if consignee_code:
        query["consigneeCode"] = {"$regex": re.escape(consignee_code), "$options": "i"}
    if date:
        query["challanDate"] = {"$regex": re.escape(date)}

    total = await db.documents.count_documents(query)
    cursor = db.documents.find(query).sort("createdAt", -1).skip((page - 1) * limit).limit(limit)
    items = [_serialize_document(doc) async for doc in cursor]
    return DocumentListResponse(items=items, total=total, page=page, limit=limit)


def ist_today_utc_range(now_ist: datetime) -> tuple[datetime, datetime]:
    """Returns the [start, end) of "today" in IST, expressed as UTC instants - so a
    processedAt query against UTC-stored timestamps matches the user's actual IST day."""
    start_of_day_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_of_day_ist.astimezone(UTC), (start_of_day_ist + timedelta(days=1)).astimezone(UTC)


@router.get("/stats", response_model=StatsResponse)
async def get_stats(current_user: CurrentUser = Depends(get_current_user)) -> StatsResponse:
    db = get_database()
    base = {"userId": current_user.id, "isDeleted": False}

    today_start_utc, today_end_utc = ist_today_utc_range(datetime.now(IST))

    total = await db.documents.count_documents(base)
    processed = await db.documents.count_documents({**base, "uploadStatus": "processed"})
    failed = await db.documents.count_documents({**base, "uploadStatus": "failed"})
    processed_today = await db.documents.count_documents(
        {**base, "processedAt": {"$gte": today_start_utc, "$lt": today_end_utc}}
    )
    low_confidence = await db.documents.count_documents({**base, "hasLowConfidenceFields": True})
    multi_page = await db.documents.count_documents({**base, "multiPage": True})

    return StatsResponse(
        total=total,
        processed=processed,
        failed=failed,
        processed_today=processed_today,
        low_confidence=low_confidence,
        multi_page=multi_page,
    )


@router.get("/{document_id}")
async def get_document(
    document_id: str, current_user: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    db = get_database()
    doc = await _get_owned_document(db, document_id, current_user.id)
    return _serialize_document(doc)


@router.get("/{document_id}/download/part1")
async def download_part1(
    document_id: str, current_user: CurrentUser = Depends(get_current_user)
) -> Response:
    db = get_database()
    doc = await _get_owned_document(db, document_id, current_user.id)
    if doc.get("part1FilePurged"):
        raise HTTPException(status_code=400, detail="Part 1 file has been purged.")
    data = await download_buffer(doc["part1GridFsFileId"])
    filename = doc.get("part1OriginalFilename") or "part1"
    return Response(
        content=data,
        media_type=doc.get("part1MimeType") or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{document_id}/download/part2")
async def download_part2(
    document_id: str, current_user: CurrentUser = Depends(get_current_user)
) -> Response:
    db = get_database()
    doc = await _get_owned_document(db, document_id, current_user.id)
    if doc.get("part2FilePurged"):
        raise HTTPException(status_code=400, detail="Part 2 file has been purged.")
    data = await download_buffer(doc["part2GridFsFileId"])
    filename = doc.get("part2OriginalFilename") or "part2"
    return Response(
        content=data,
        media_type=doc.get("part2MimeType") or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{document_id}/reprocess", status_code=202)
async def reprocess_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, str]:
    db = get_database()
    doc = await _get_owned_document(db, document_id, current_user.id)
    if doc.get("part1FilePurged") or doc.get("part2FilePurged"):
        raise HTTPException(
            status_code=400, detail="Cannot reprocess - the original file(s) have been purged."
        )

    part1_bytes = await download_buffer(doc["part1GridFsFileId"])
    part2_bytes = await download_buffer(doc["part2GridFsFileId"])

    await db.documents.update_one(
        {"_id": doc["_id"]},
        {"$set": {"uploadStatus": "processing", "updatedAt": datetime.now(UTC)}},
    )
    background_tasks.add_task(
        _run_pipeline_and_update,
        doc["_id"],
        part1_bytes,
        doc["part1MimeType"],
        part2_bytes,
        doc["part2MimeType"],
        is_reprocess=True,
    )
    await log_action(current_user.id, "document_reprocessed", {"documentId": document_id})
    return {"message": "Reprocessing started."}


@router.patch("/{document_id}/correct")
async def correct_document(
    document_id: str, body: CorrectRequest, current_user: CurrentUser = Depends(get_current_user)
) -> dict[str, str]:
    db = get_database()
    doc = await _get_owned_document(db, document_id, current_user.id)
    await apply_field_correction(
        db, doc, body.field, body.value, actor_user_id=current_user.id, by_admin=False
    )
    return {"message": "Field updated."}


@router.delete("/{document_id}")
async def soft_delete_document(
    document_id: str, current_user: CurrentUser = Depends(get_current_user)
) -> dict[str, str]:
    db = get_database()
    doc = await _get_owned_document(db, document_id, current_user.id)
    now = datetime.now(UTC)
    await db.documents.update_one(
        {"_id": doc["_id"]}, {"$set": {"isDeleted": True, "deletedAt": now, "updatedAt": now}}
    )
    await _best_effort_purge_files(doc)
    await log_action(current_user.id, "document_deleted", {"documentId": document_id})
    return {"message": "Document deleted."}


@router.post("/{document_id}/purge-files")
async def purge_document_files(
    document_id: str, current_user: CurrentUser = Depends(get_current_user)
) -> dict[str, str]:
    db = get_database()
    doc = await _get_owned_document(db, document_id, current_user.id)
    now = datetime.now(UTC)
    updates: dict[str, Any] = {}

    if doc.get("part1GridFsFileId") and not doc.get("part1FilePurged"):
        await delete_file(doc["part1GridFsFileId"])
        updates["part1FilePurged"] = True
        updates["part1FilePurgedAt"] = now
    if doc.get("part2GridFsFileId") and not doc.get("part2FilePurged"):
        await delete_file(doc["part2GridFsFileId"])
        updates["part2FilePurged"] = True
        updates["part2FilePurgedAt"] = now

    if updates:
        updates["updatedAt"] = now
        await db.documents.update_one({"_id": doc["_id"]}, {"$set": updates})

    await log_action(current_user.id, "document_file_purged", {"documentId": document_id})
    return {"message": "Original files purged. Extracted data was preserved."}
