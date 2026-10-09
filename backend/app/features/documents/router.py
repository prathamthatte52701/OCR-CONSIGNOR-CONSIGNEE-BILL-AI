"""Document routes: dual-file upload, list/search, edit, reprocess, and the two delete
tiers (delete - permanent, both record and files; purge-files - files only, record kept).
Per-user data isolation on every query - every filter includes userId, malformed ids return
400, other users' documents 404. Bulk age/date-range purge ("nuke") lives in
app.features.admin.router - admin-only now, not user-facing."""

import io
import re
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.audit_log import log_action
from app.core.database import get_database
from app.core.filenames import attachment_header, safe_filename
from app.core.object_id import is_valid_object_id
from app.core.orphaned_files import record_orphan
from app.features.auth.dependencies import CurrentUser, get_current_user
from app.features.documents.correction_service import apply_field_correction
from app.features.documents.gridfs_service import delete_file, download_buffer, upload_buffer
from app.features.documents.processing import run_full_pipeline
from app.features.documents.schemas import (
    CorrectRequest,
    DocumentListResponse,
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
    # isDeleted: soft-delete was removed (delete is permanent now), but a leftover document
    # still flagged isDeleted=True must never resurface for its owner.
    doc = await db.documents.find_one(
        {"_id": ObjectId(document_id), "userId": user_id, "isDeleted": {"$ne": True}}
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
            except Exception as exc:  # noqa: BLE001 - best-effort, never blocks the delete
                await record_orphan(file_id, doc.get("_id"), doc.get("userId"), exc)


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


_READ_CHUNK = 64 * 1024


async def _read_capped(upload: UploadFile, label: str) -> bytes:
    """Reads an uploaded file in chunks, aborting the moment it passes MAX_FILE_SIZE."""
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(_READ_CHUNK):
        total += len(chunk)
        if total > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"{label} file exceeds the 5MB limit.")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/upload", status_code=201, response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    part1: UploadFile = File(...),
    part2: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> UploadResponse:
    # The middleware in main.py already refused an oversized request by Content-Length and
    # cuts a streamed one off; each file is ALSO capped here while it is being read, so one
    # file can never be pulled fully into memory past the limit (Part 1 is checked before
    # Part 2 is even read).
    part1_bytes = await _read_capped(part1, "Part 1")
    part2_bytes = await _read_capped(part2, "Part 2")
    for label, data in (("Part 1", part1_bytes), ("Part 2", part2_bytes)):
        if not data:
            raise HTTPException(status_code=400, detail=f"{label} file is empty.")

    part1_mime = _sniff_mime_type(part1_bytes)
    part2_mime = _sniff_mime_type(part2_bytes)
    if part1_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Part 1 file type not supported.")
    if part2_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Part 2 file type not supported.")

    part1_name = safe_filename(part1.filename, "part1")
    part2_name = safe_filename(part2.filename, "part2")
    db = get_database()
    part1_file_id = await upload_buffer(part1_bytes, part1_name, part1_mime)
    part2_file_id = await upload_buffer(part2_bytes, part2_name, part2_mime)

    now = datetime.now(UTC)
    result = await db.documents.insert_one(
        {
            "userId": current_user.id,
            "uploadStatus": "processing",
            "edited": False,
            "hasLowConfidenceFields": False,
            "multiPage": False,
            "recoveryAttempts": 0,
            "part1GridFsFileId": part1_file_id,
            "part1OriginalFilename": part1_name,
            "part1MimeType": part1_mime,
            "part1Size": len(part1_bytes),
            "part1FilePurged": False,
            "part2GridFsFileId": part2_file_id,
            "part2OriginalFilename": part2_name,
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


def _upload_range_start_utc(range_key: str, now: datetime) -> datetime:
    """Start of the UTC "upload date" bucket for `range_key` (today/week/month/year),
    evaluated against `now` (must be tz-aware UTC). Week starts Monday. No upper bound is
    needed: createdAt is always <= the instant the query runs, so an open-ended $gte is
    equivalent to a [start, now) window without racing the clock between capturing `now`
    and executing the query."""
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if range_key == "today":
        return start_of_day
    if range_key == "week":
        return start_of_day - timedelta(days=now.weekday())  # Monday == weekday() 0
    if range_key == "month":
        return start_of_day.replace(day=1)
    if range_key == "year":
        return start_of_day.replace(month=1, day=1)
    raise ValueError(f"Unknown range: {range_key}")  # unreachable - Query() pattern validates first


def _build_list_query(
    current_user: CurrentUser,
    invoice_no: str | None,
    consignee_code: str | None,
    date: str | None,
    date_range: str | None,
) -> dict[str, Any]:
    query: dict[str, Any] = {"userId": current_user.id, "isDeleted": {"$ne": True}}
    if invoice_no:
        query["invoiceNo"] = {"$regex": re.escape(invoice_no), "$options": "i"}
    if consignee_code:
        query["consigneeCode"] = {"$regex": re.escape(consignee_code), "$options": "i"}
    if date:
        query["challanDate"] = {"$regex": re.escape(date)}
    if date_range:
        query["createdAt"] = {"$gte": _upload_range_start_utc(date_range, datetime.now(UTC))}
    return query


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    current_user: CurrentUser = Depends(get_current_user),
    invoice_no: str | None = Query(None, alias="invoiceNo"),
    consignee_code: str | None = Query(None, alias="consigneeCode"),
    date: str | None = Query(None),
    date_range: str | None = Query(None, alias="range", pattern="^(today|week|month|year)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
) -> DocumentListResponse:
    db = get_database()
    query = _build_list_query(current_user, invoice_no, consignee_code, date, date_range)

    total = await db.documents.count_documents(query)
    cursor = db.documents.find(query).sort("createdAt", -1).skip((page - 1) * limit).limit(limit)
    items = [_serialize_document(doc) async for doc in cursor]
    return DocumentListResponse(items=items, total=total, page=page, limit=limit)


@router.post("/download-all")
async def download_all(
    current_user: CurrentUser = Depends(get_current_user),
    invoice_no: str | None = Query(None, alias="invoiceNo"),
    consignee_code: str | None = Query(None, alias="consigneeCode"),
    date: str | None = Query(None),
    date_range: str | None = Query(None, alias="range", pattern="^(today|week|month|year)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
) -> Response:
    """Zips up the original Part1+Part2 files for exactly the current page of `list_documents`
    (same filters, same skip/limit) - not the whole filtered set, not other pages. Any document
    with a purged file, a missing GridFS id, or a download that raises is skipped entirely
    (never a partial per-document zip entry) so one bad file can't 500 the whole export."""
    db = get_database()
    query = _build_list_query(current_user, invoice_no, consignee_code, date, date_range)
    cursor = db.documents.find(query).sort("createdAt", -1).skip((page - 1) * limit).limit(limit)
    docs = [doc async for doc in cursor]

    included = 0
    skipped = 0
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for doc in docs:
            if doc.get("part1FilePurged") or doc.get("part2FilePurged"):
                skipped += 1
                continue
            part1_file_id = doc.get("part1GridFsFileId")
            part2_file_id = doc.get("part2GridFsFileId")
            if not part1_file_id or not part2_file_id:
                skipped += 1
                continue
            try:
                part1_data = await download_buffer(part1_file_id)
                part2_data = await download_buffer(part2_file_id)
            except Exception:  # noqa: BLE001 - one unreadable file must not 500 the whole zip
                skipped += 1
                continue

            # Both come from untrusted text (the OCR'd invoice number, the uploaded filename):
            # sanitised so an entry can never contain "../" or an absolute path (zip slip).
            folder = safe_filename(doc.get("invoiceNo"), str(doc["_id"]))
            part1_name = safe_filename(doc.get("part1OriginalFilename"), "part1")
            part2_name = safe_filename(doc.get("part2OriginalFilename"), "part2")
            zf.writestr(f"{folder}/part1_{part1_name}", part1_data)
            zf.writestr(f"{folder}/part2_{part2_name}", part2_data)
            included += 1

    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="documents.zip"',
            "X-Included-Count": str(included),
            "X-Skipped-Count": str(skipped),
        },
    )


def ist_today_utc_range(now_ist: datetime) -> tuple[datetime, datetime]:
    """Returns the [start, end) of "today" in IST, expressed as UTC instants - so a
    processedAt query against UTC-stored timestamps matches the user's actual IST day."""
    start_of_day_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_of_day_ist.astimezone(UTC), (start_of_day_ist + timedelta(days=1)).astimezone(UTC)


@router.get("/stats", response_model=StatsResponse)
async def get_stats(current_user: CurrentUser = Depends(get_current_user)) -> StatsResponse:
    db = get_database()
    base = {"userId": current_user.id, "isDeleted": {"$ne": True}}

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
    return Response(
        content=data,
        media_type=doc.get("part1MimeType") or "application/octet-stream",
        headers=attachment_header(doc.get("part1OriginalFilename"), "part1"),
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
    return Response(
        content=data,
        media_type=doc.get("part2MimeType") or "application/octet-stream",
        headers=attachment_header(doc.get("part2OriginalFilename"), "part2"),
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
        {
            "$set": {
                "uploadStatus": "processing",
                "recoveryAttempts": 0,  # a fresh run gets a fresh restart-recovery budget
                "updatedAt": datetime.now(UTC),
            }
        },
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
async def delete_document(
    document_id: str, current_user: CurrentUser = Depends(get_current_user)
) -> dict[str, str]:
    """Permanently deletes the document record and its original files. File deletion is
    best-effort (tracked via app.core.orphaned_files on failure, see _best_effort_purge_files)
    and never blocks the record removal - a GridFS outage must not leave a document the user
    asked to delete still visible to them."""
    db = get_database()
    doc = await _get_owned_document(db, document_id, current_user.id)
    await _best_effort_purge_files(doc)
    await db.documents.delete_one({"_id": doc["_id"]})
    await db.corrections.delete_many({"documentId": doc["_id"]})
    await log_action(current_user.id, "document_deleted", {"documentId": document_id})
    return {"message": "Document permanently deleted."}


@router.post("/{document_id}/purge-files")
async def purge_document_files(
    document_id: str, current_user: CurrentUser = Depends(get_current_user)
) -> dict[str, str]:
    db = get_database()
    doc = await _get_owned_document(db, document_id, current_user.id)
    now = datetime.now(UTC)
    updates: dict[str, Any] = {}

    if doc.get("part1GridFsFileId") and not doc.get("part1FilePurged"):
        try:
            await delete_file(doc["part1GridFsFileId"])
        except Exception as exc:  # noqa: BLE001 - tracked, then re-raised unchanged
            await record_orphan(doc["part1GridFsFileId"], doc["_id"], doc.get("userId"), exc)
            raise
        updates["part1FilePurged"] = True
        updates["part1FilePurgedAt"] = now
    if doc.get("part2GridFsFileId") and not doc.get("part2FilePurged"):
        try:
            await delete_file(doc["part2GridFsFileId"])
        except Exception as exc:  # noqa: BLE001 - tracked, then re-raised unchanged
            await record_orphan(doc["part2GridFsFileId"], doc["_id"], doc.get("userId"), exc)
            raise
        updates["part2FilePurged"] = True
        updates["part2FilePurgedAt"] = now

    if updates:
        updates["updatedAt"] = now
        await db.documents.update_one({"_id": doc["_id"]}, {"$set": updates})

    await log_action(current_user.id, "document_file_purged", {"documentId": document_id})
    return {"message": "Original files purged. Extracted data was preserved."}
