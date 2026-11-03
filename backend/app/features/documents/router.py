"""Document routes: dual-file upload, list/search, edit, reprocess, and the two delete
tiers (delete - permanent, both record and files; purge-files - files only, record kept).
Per-user data isolation on every query - every filter includes userId, malformed ids return
400, other users' documents 404. Bulk age/date-range purge ("nuke") lives in
app.features.admin.router - admin-only now, not user-facing."""

import asyncio
import io
import logging
import re
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.audit_log import log_action
from app.core.database import get_database
from app.core.filenames import attachment_header, safe_filename
from app.core.image_limits import ImageTooLarge, check_upload
from app.core.object_id import is_valid_object_id
from app.core.orphaned_files import record_orphan
from app.core.rate_limit import BULK_UPLOAD_LIMIT, UPLOAD_LIMIT, limiter
from app.features.auth.dependencies import CurrentUser, get_current_user
from app.features.documents.correction_service import apply_field_correction
from app.features.documents.file_purge import (
    DELETE_FAILED_MESSAGE,
    DELETE_OK_MESSAGE,
    PURGE_FAILED_MESSAGE,
    PURGE_OK_MESSAGE,
    best_effort_purge_files,
    purge_parts,
)
from app.features.documents.gridfs_service import delete_file, download_buffer, upload_buffer
from app.features.documents.processing import run_full_pipeline
from app.features.documents.review_warnings import review_warnings
from app.features.documents.schemas import (
    CorrectRequest,
    DocumentListResponse,
    StatsResponse,
    UploadResponse,
)
from app.features.ocr.preprocessing import get_pdf_page_count

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger(__name__)

router = APIRouter()

MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_BULK_SETS = 5
MAX_PDF_PAGES = 4
# A job lost without a restart must not block Reprocess forever; the OCR queue can legitimately
# keep a document "processing" for many minutes, so the window is long.
REPROCESS_STUCK_AFTER = timedelta(minutes=30)
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


async def _run_pipeline_and_update(
    doc_id: ObjectId,
    part1_bytes: bytes,
    part1_mime: str,
    part2_bytes: bytes,
    part2_mime: str,
    *,
    is_reprocess: bool,
    run_id: str | None,
) -> None:
    db = get_database()
    # Only the job holding the document's CURRENT run id may write; None matches a document
    # that has no processingRunId at all (older rows).
    run_filter = {"_id": doc_id, "processingRunId": run_id}
    try:
        # Skip a job that went stale while queued (deleted / reprocessed) before it takes the OCR
        # slot. Known limit: a job already WAITING for the slot inside the pipeline is not
        # re-checked; only the start of a job is. Inside the try, so a failing read marks the
        # document failed instead of leaving it "processing" until the next restart.
        if await db.documents.find_one(run_filter, {"_id": 1}) is None:
            logger.info("stale run skipped before start: document %s", doc_id)
            return
        # One OCR reader at a time is enforced INSIDE the pipeline (ocr/ocr_slot.py), around the
        # two heavy engine calls only; a waiting job simply stays "processing".
        update = await run_full_pipeline(part1_bytes, part1_mime, part2_bytes, part2_mime)
        now = datetime.now(UTC)
        update["uploadStatus"] = "processed"
        update["processingError"] = None
        update["processedAt"] = now
        update["updatedAt"] = now
        if is_reprocess:
            update["reprocessedAt"] = now
            update["edited"] = False
        written = await db.documents.update_one(run_filter, {"$set": update})
        if written.matched_count == 0:
            logger.info("stale run ignored: document %s", doc_id)
    except Exception as exc:  # noqa: BLE001 - pipeline failure must not crash the background task
        failed = await db.documents.update_one(
            run_filter,
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
        if failed.matched_count == 0:
            logger.info("stale run ignored: document %s", doc_id)


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


async def _validate_part(label: str, data: bytes, mime: str | None) -> str:
    """Every per-file rule for one part; raises HTTPException naming the part. Stores nothing."""
    if not data:
        raise HTTPException(status_code=400, detail=f"{label} file is empty.")
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"{label} file type not supported.")
    if mime == "application/pdf":
        # Only the page COUNT is limited; the pipeline still reads page 1 only.
        pages = await get_pdf_page_count(data)
        if not pages:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{label}: Could not read this PDF. "
                    "Please upload a valid PDF or convert it to JPG/PNG."
                ),
            )
        if pages > MAX_PDF_PAGES:
            raise HTTPException(
                status_code=400, detail=f"{label}: PDF must be {MAX_PDF_PAGES} pages or less."
            )
    try:
        await check_upload(data, mime)
    except ImageTooLarge as exc:
        raise HTTPException(status_code=400, detail=f"{label}: {exc}") from None
    return mime


async def _rollback_stored(stored: list[ObjectId], user_id: ObjectId) -> None:
    """Deletes every file stored so far; a failed delete is recorded as an orphan. Never raises,
    so one bad file cannot stop the others from being cleaned up."""
    for file_id in stored:
        try:
            await delete_file(file_id)
        except Exception as del_exc:  # noqa: BLE001
            try:
                await record_orphan(file_id, None, user_id, del_exc)
            except Exception:  # noqa: BLE001 - never abort the rollback of the other file
                pass


async def _store_upload(
    user_id: ObjectId,
    part1: tuple[str, bytes, str],
    part2: tuple[str, bytes, str],
    run_id: str,
) -> ObjectId:
    """Stores both files and the document row; returns the document id. On any failure every
    stored file is deleted (also on cancellation, shielded) and a clean 500 is raised."""
    (name1, bytes1, mime1), (name2, bytes2, mime2) = part1, part2
    db = get_database()
    stored: list[ObjectId] = []
    try:
        file1 = await upload_buffer(bytes1, name1, mime1)
        stored.append(file1)
        file2 = await upload_buffer(bytes2, name2, mime2)
        stored.append(file2)
        now = datetime.now(UTC)
        result = await db.documents.insert_one(
            {
                "userId": user_id,
                "uploadStatus": "processing",
                "edited": False,
                "hasLowConfidenceFields": False,
                "multiPage": False,
                "recoveryAttempts": 0,
                "processingRunId": run_id,
                "part1GridFsFileId": file1,
                "part1OriginalFilename": name1,
                "part1MimeType": mime1,
                "part1Size": len(bytes1),
                "part1FilePurged": False,
                "part2GridFsFileId": file2,
                "part2OriginalFilename": name2,
                "part2MimeType": mime2,
                "part2Size": len(bytes2),
                "part2FilePurged": False,
                "createdAt": now,
                "updatedAt": now,
            }
        )
        inserted_id: ObjectId = result.inserted_id
        return inserted_id
    except BaseException as exc:
        if isinstance(exc, Exception) and len(stored) == 2:
            # The insert may have committed and only its acknowledgement been lost: a document
            # that already points at this file means the upload SUCCEEDED - deleting the files
            # now would destroy a live record.
            try:
                found = await db.documents.find_one(
                    {"userId": user_id, "part1GridFsFileId": stored[0]}, {"_id": 1}
                )
            except Exception as lookup_exc:  # noqa: BLE001
                # Unknown outcome: delete nothing and record no orphans (a retry of an orphan
                # could delete a live file). Leave the files for manual review.
                logger.error("upload insert lookup failed: class=%s", type(lookup_exc).__name__)
                raise HTTPException(
                    status_code=500, detail="Upload failed. Please try again."
                ) from None
            if found is not None:
                found_id: ObjectId = found["_id"]
                return found_id
        await asyncio.shield(_rollback_stored(stored, user_id))
        if not isinstance(exc, Exception):
            raise  # CancelledError etc. - cleaned up, now propagate
        logger.error("upload failed, rolled back: class=%s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Upload failed. Please try again.") from None


@router.post("/upload", status_code=201, response_model=UploadResponse)
@limiter.limit(UPLOAD_LIMIT)
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    part1: UploadFile = File(...),
    part2: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> UploadResponse:
    # Per-IP rate limited: every upload triggers OCR + LLM work.
    # The middleware in main.py already refused an oversized request by Content-Length and
    # cuts a streamed one off; each file is ALSO capped here while it is being read.
    part1_bytes = await _read_capped(part1, "Part 1")
    part2_bytes = await _read_capped(part2, "Part 2")
    # Both parts are fully validated BEFORE anything is stored.
    part1_mime = await _validate_part("Part 1", part1_bytes, _sniff_mime_type(part1_bytes))
    part2_mime = await _validate_part("Part 2", part2_bytes, _sniff_mime_type(part2_bytes))

    run_id = uuid.uuid4().hex
    doc_id = await _store_upload(
        current_user.id,
        (safe_filename(part1.filename, "part1"), part1_bytes, part1_mime),
        (safe_filename(part2.filename, "part2"), part2_bytes, part2_mime),
        run_id,
    )

    background_tasks.add_task(
        _run_pipeline_and_update,
        doc_id,
        part1_bytes,
        part1_mime,
        part2_bytes,
        part2_mime,
        is_reprocess=False,
        run_id=run_id,
    )
    await log_action(current_user.id, "document_uploaded", {"documentId": str(doc_id)})
    return UploadResponse(id=str(doc_id), upload_status="processing")


_PipelineJob = tuple[ObjectId, bytes, str, bytes, str, str]


async def _run_sequentially(jobs: list[_PipelineJob]) -> None:
    """Reads the created sets strictly one after another; a crash on one set marks only that
    document failed and the next set still runs."""
    for doc_id, b1, m1, b2, m2, run_id in jobs:
        try:
            await _run_pipeline_and_update(
                doc_id, b1, m1, b2, m2, is_reprocess=False, run_id=run_id
            )
        except Exception as exc:  # noqa: BLE001 - never let one set stop the rest
            logger.error("bulk set %s crashed the pipeline: class=%s", doc_id, type(exc).__name__)
            try:
                await get_database().documents.update_one(
                    {"_id": doc_id, "processingRunId": run_id},
                    {
                        "$set": {
                            "uploadStatus": "failed",
                            "processingError": type(exc).__name__,
                            "updatedAt": datetime.now(UTC),
                        }
                    },
                )
            except Exception:  # noqa: BLE001
                pass


@router.post("/bulk-upload", status_code=201)
@limiter.limit(BULK_UPLOAD_LIMIT)
async def bulk_upload_documents(
    request: Request,
    background_tasks: BackgroundTasks,
    part1: list[UploadFile] = File(default=[]),
    part2: list[UploadFile] = File(default=[]),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Up to MAX_BULK_SETS sets (Part 1 + Part 2, matched by position). Each set is validated
    and stored on its own - a bad set is reported and skipped, the others go through - and the
    created sets are then read one after another in ONE background task."""
    if not part1 and not part2:
        raise HTTPException(status_code=400, detail="Please add at least one set.")
    if len(part1) != len(part2):
        raise HTTPException(status_code=400, detail="Each set needs both Part 1 and Part 2.")
    if len(part1) > MAX_BULK_SETS:
        raise HTTPException(
            status_code=400, detail=f"You can upload at most {MAX_BULK_SETS} sets at once."
        )

    results: list[dict[str, Any]] = []
    jobs: list[_PipelineJob] = []
    for index, (file1, file2) in enumerate(zip(part1, part2, strict=True)):
        try:
            bytes1 = await _read_capped(file1, "Part 1")
            bytes2 = await _read_capped(file2, "Part 2")
            mime1 = await _validate_part("Part 1", bytes1, _sniff_mime_type(bytes1))
            mime2 = await _validate_part("Part 2", bytes2, _sniff_mime_type(bytes2))
            run_id = uuid.uuid4().hex
            doc_id = await _store_upload(
                current_user.id,
                (safe_filename(file1.filename, "part1"), bytes1, mime1),
                (safe_filename(file2.filename, "part2"), bytes2, mime2),
                run_id,
            )
        except HTTPException as exc:
            results.append({"index": index, "error": f"Set {index + 1}, {exc.detail}"})
            continue
        except Exception as exc:  # noqa: BLE001 - one broken set must never lose the others
            logger.error("bulk set %d failed unexpectedly: class=%s", index + 1, type(exc).__name__)
            results.append(
                {"index": index, "error": f"Set {index + 1}, Upload failed. Please try again."}
            )
            continue
        # The set exists: record it FIRST, so nothing after this point can lose it.
        jobs.append((doc_id, bytes1, mime1, bytes2, mime2, run_id))
        results.append({"index": index, "id": str(doc_id)})
        try:
            await log_action(current_user.id, "document_uploaded", {"documentId": str(doc_id)})
        except Exception as exc:  # noqa: BLE001 - an audit hiccup must not fail a stored set
            logger.error("bulk audit log failed: class=%s", type(exc).__name__)

    if jobs:
        background_tasks.add_task(_run_sequentially, jobs)
    return {"results": results}


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
    serialized = _serialize_document(doc)
    serialized["reviewWarnings"] = review_warnings(doc)  # computed on read, not stored
    return serialized


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

    # Atomic claim: only one concurrent Reprocess can win (double click / two tabs).
    now = datetime.now(UTC)
    run_id = uuid.uuid4().hex
    claim = await db.documents.update_one(
        {
            "_id": doc["_id"],
            "$or": [
                {"uploadStatus": {"$in": ["processed", "failed"]}},
                {
                    "uploadStatus": "processing",
                    "updatedAt": {"$lte": now - REPROCESS_STUCK_AFTER},
                },
            ],
        },
        {
            "$set": {
                "uploadStatus": "processing",
                "processingRunId": run_id,
                "recoveryAttempts": 0,  # a fresh run gets a fresh restart-recovery budget
                "processingError": None,
                "updatedAt": now,
            }
        },
    )
    if claim.matched_count == 0:
        raise HTTPException(
            status_code=409, detail="This document is already being processed. Please wait."
        )
    background_tasks.add_task(
        _run_pipeline_and_update,
        doc["_id"],
        part1_bytes,
        doc["part1MimeType"],
        part2_bytes,
        doc["part2MimeType"],
        is_reprocess=True,
        run_id=run_id,
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
) -> dict[str, Any]:
    """Permanently deletes the document record and its original files. File deletion is
    best-effort (orphans are tracked on failure, see file_purge.best_effort_purge_files)
    and never blocks the record removal - a GridFS outage must not leave a document the user
    asked to delete still visible to them."""
    db = get_database()
    doc = await _get_owned_document(db, document_id, current_user.id)
    cleanup_failed = await best_effort_purge_files(doc)
    await db.documents.delete_one({"_id": doc["_id"]})
    await db.corrections.delete_many({"documentId": doc["_id"]})
    await log_action(current_user.id, "document_deleted", {"documentId": document_id})
    message = DELETE_FAILED_MESSAGE if cleanup_failed else DELETE_OK_MESSAGE
    return {"message": message, "gridFsCleanupFailed": cleanup_failed}


@router.post("/{document_id}/purge-files")
async def purge_document_files(
    document_id: str, current_user: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    """Purges BOTH original files together. A failed delete is recorded as an orphan and never
    blocks: both parts are still marked purged and the dead file reference is cleared."""
    db = get_database()
    doc = await _get_owned_document(db, document_id, current_user.id)
    now = datetime.now(UTC)
    updates, cleanup_failed = await purge_parts(doc, now)

    if updates:
        updates["updatedAt"] = now
        await db.documents.update_one({"_id": doc["_id"]}, {"$set": updates})

    await log_action(current_user.id, "document_file_purged", {"documentId": document_id})
    message = PURGE_FAILED_MESSAGE if cleanup_failed else PURGE_OK_MESSAGE
    return {"message": message, "gridFsCleanupFailed": cleanup_failed}
