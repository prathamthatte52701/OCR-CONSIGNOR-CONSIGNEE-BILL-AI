"""Admin routes: every route behind require_admin. Cross-user CRUD on users/documents,
telemetry, audit log viewer, and bulk "nuke" deletion (per-user or global, age-based or
Year+Month, double-password + rate-limited - see nuke_user/nuke_global). Role is always
re-verified server-side via require_admin's DB lookup - never trusted from a JWT claim."""

from datetime import UTC, datetime, timedelta
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.audit_log import log_action
from app.core.database import get_database
from app.core.object_id import is_valid_object_id
from app.core.orphaned_files import record_orphan
from app.core.security import verify_password
from app.core.validators import is_valid_email, is_valid_username, normalize_email
from app.features.admin.schemas import (
    AdminNukeRequest,
    ListResponse,
    TelemetryResponse,
    UpdateUserRequest,
)
from app.features.auth.dependencies import CurrentUser, require_admin
from app.features.documents.correction_service import apply_field_correction
from app.features.documents.gridfs_service import delete_file
from app.features.documents.schemas import CorrectRequest

router = APIRouter()

NUKE_ATTEMPT_ACTION = "admin_nuke_attempt"
NUKE_RATE_LIMIT_WINDOW_HOURS = 24
NUKE_RATE_LIMIT_MAX_ATTEMPTS = 5
CONFIRMATION_PHRASE_USER_NUKE = "NUKE USER"
CONFIRMATION_PHRASE_GLOBAL_NUKE = "NUKE ALL"


def _serialize_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(user["_id"]),
        "username": user["username"],
        "email": user["email"],
        "role": user.get("role", "user"),
        "createdAt": user.get("createdAt"),
        "updatedAt": user.get("updatedAt"),
    }


def _serialize_document(doc: dict[str, Any], owner: dict[str, Any] | None) -> dict[str, Any]:
    result = dict(doc)
    result["id"] = str(result.pop("_id"))
    result["userId"] = str(result["userId"])
    result.pop("part1GridFsFileId", None)
    result.pop("part2GridFsFileId", None)
    result["ownerUsername"] = owner["username"] if owner else None
    result["ownerEmail"] = owner["email"] if owner else None
    return result


def _serialize_orphan(record: dict[str, Any]) -> dict[str, Any]:
    result = dict(record)
    result["id"] = str(result.pop("_id"))
    result["fileId"] = str(result["fileId"])
    result["documentId"] = str(result["documentId"]) if result.get("documentId") else None
    result["userId"] = str(result["userId"]) if result.get("userId") else None
    return result


async def _best_effort_purge_files(doc: dict[str, Any]) -> None:
    for key in ("part1GridFsFileId", "part2GridFsFileId"):
        file_id = doc.get(key)
        if file_id:
            try:
                await delete_file(file_id)
            except Exception as exc:  # noqa: BLE001 - best-effort, never blocks the delete
                await record_orphan(file_id, doc.get("_id"), doc.get("userId"), exc)


def _build_range_filter(
    user_id: ObjectId | None,
    older_than_months: int | None,
    year: int | None,
    month: int | None,
) -> dict[str, Any]:
    """user_id=None means global (no userId filter). Exactly one of older_than_months/year
    is required; month is optional and only meaningful alongside year (Year+Month mode -
    without month, year alone nukes the whole calendar year)."""
    if (older_than_months is None) == (year is None):
        raise HTTPException(
            status_code=400, detail="Provide exactly one of olderThanMonths or year."
        )
    if month is not None and year is None:
        raise HTTPException(status_code=400, detail="month requires year.")

    query: dict[str, Any] = {}
    if user_id is not None:
        query["userId"] = user_id

    if older_than_months is not None:
        if older_than_months not in (3, 6, 9):
            raise HTTPException(status_code=400, detail="olderThanMonths must be 3, 6, or 9.")
        cutoff = datetime.now(UTC) - timedelta(days=30 * older_than_months)
        query["createdAt"] = {"$lt": cutoff}
    else:
        assert year is not None  # guaranteed by the XOR check above
        if month is not None:
            if not 1 <= month <= 12:
                raise HTTPException(status_code=400, detail="month must be 1-12.")
            start = datetime(year, month, 1, tzinfo=UTC)
            end = (
                datetime(year + 1, 1, 1, tzinfo=UTC)
                if month == 12
                else datetime(year, month + 1, 1, tzinfo=UTC)
            )
        else:
            start = datetime(year, 1, 1, tzinfo=UTC)
            end = datetime(year + 1, 1, 1, tzinfo=UTC)
        query["createdAt"] = {"$gte": start, "$lt": end}
    return query


async def _enforce_nuke_rate_limit(db: AsyncIOMotorDatabase, admin_id: ObjectId) -> None:
    window_start = datetime.now(UTC) - timedelta(hours=NUKE_RATE_LIMIT_WINDOW_HOURS)
    count = await db.auditlogs.count_documents(
        {"userId": admin_id, "action": NUKE_ATTEMPT_ACTION, "createdAt": {"$gte": window_start}}
    )
    if count >= NUKE_RATE_LIMIT_MAX_ATTEMPTS:
        await log_action(admin_id, "admin_nuke_rate_limited", {})
        raise HTTPException(
            status_code=429,
            detail=f"Too many nuke attempts. Try again after {NUKE_RATE_LIMIT_WINDOW_HOURS}h.",
        )


async def _nuke_documents(db: AsyncIOMotorDatabase, query: dict[str, Any]) -> int:
    docs = await db.documents.find(query).to_list(length=None)
    for doc in docs:
        await _best_effort_purge_files(doc)
    doc_ids = [doc["_id"] for doc in docs]
    result = await db.documents.delete_many(query)
    if doc_ids:
        await db.corrections.delete_many({"documentId": {"$in": doc_ids}})
    return result.deleted_count


@router.get("/ping")
async def ping(current_user: CurrentUser = Depends(require_admin)) -> dict[str, str]:
    return {"message": "pong", "admin": current_user.username}


@router.get("/users", response_model=ListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
    current_user: CurrentUser = Depends(require_admin),
) -> ListResponse:
    db = get_database()
    total = await db.users.count_documents({})
    cursor = db.users.find({}).sort("createdAt", -1).skip((page - 1) * limit).limit(limit)
    items = [_serialize_user(user) async for user in cursor]
    return ListResponse(items=items, total=total, page=page, limit=limit)


@router.get("/users/{user_id}")
async def get_user(
    user_id: str, current_user: CurrentUser = Depends(require_admin)
) -> dict[str, Any]:
    if not is_valid_object_id(user_id):
        raise HTTPException(status_code=400, detail="Invalid user id.")
    db = get_database()
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return _serialize_user(user)


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str, body: UpdateUserRequest, current_user: CurrentUser = Depends(require_admin)
) -> dict[str, Any]:
    if not is_valid_object_id(user_id):
        raise HTTPException(status_code=400, detail="Invalid user id.")
    db = get_database()
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    updates: dict[str, Any] = {}
    if body.username is not None:
        if not is_valid_username(body.username):
            raise HTTPException(
                status_code=400, detail="Username must be 3-8 characters, no whitespace."
            )
        updates["username"] = body.username
    if body.email is not None:
        normalized_email = normalize_email(body.email)
        if not is_valid_email(normalized_email):
            raise HTTPException(status_code=400, detail="Invalid email address.")
        updates["email"] = normalized_email
    if body.role is not None:
        if body.role not in ("user", "admin"):
            raise HTTPException(status_code=400, detail="Role must be 'user' or 'admin'.")
        updates["role"] = body.role

    if updates:
        updates["updatedAt"] = datetime.now(UTC)
        await db.users.update_one({"_id": user["_id"]}, {"$set": updates})
        await log_action(
            current_user.id, "user_updated", {"userId": user_id, "fields": list(updates)}
        )

    updated = await db.users.find_one({"_id": user["_id"]})
    assert updated is not None
    return _serialize_user(updated)


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str, current_user: CurrentUser = Depends(require_admin)
) -> dict[str, str]:
    if not is_valid_object_id(user_id):
        raise HTTPException(status_code=400, detail="Invalid user id.")
    if user_id == str(current_user.id):
        raise HTTPException(status_code=400, detail="Cannot delete your own account.")

    db = get_database()
    target_id = ObjectId(user_id)
    user = await db.users.find_one({"_id": target_id})
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    docs = await db.documents.find({"userId": target_id}).to_list(length=None)
    for doc in docs:
        await _best_effort_purge_files(doc)
    await db.documents.delete_many({"userId": target_id})
    await db.corrections.delete_many({"userId": target_id})
    await db.auditlogs.delete_many({"userId": target_id})
    await db.users.delete_one({"_id": target_id})

    await log_action(current_user.id, "user_deleted", {"userId": user_id})
    return {"message": "User and all owned data deleted."}


@router.post("/users/{user_id}/nuke")
async def nuke_user(
    user_id: str, body: AdminNukeRequest, current_user: CurrentUser = Depends(require_admin)
) -> dict[str, Any]:
    """Bulk-deletes one user's documents (age-based or Year+Month), scoped to that user only.
    Requires the confirmation phrase, password entered twice (validated here - never trust the
    frontend's match check alone), and shares the 24h/5-attempt nuke rate limit with every
    other nuke variant (see _enforce_nuke_rate_limit)."""
    if not is_valid_object_id(user_id):
        raise HTTPException(status_code=400, detail="Invalid user id.")
    db = get_database()
    await _enforce_nuke_rate_limit(db, current_user.id)

    target_id = ObjectId(user_id)
    target = await db.users.find_one({"_id": target_id})
    if target is None:
        raise HTTPException(status_code=404, detail="User not found.")

    if body.confirmation_phrase != CONFIRMATION_PHRASE_USER_NUKE:
        await log_action(
            current_user.id,
            NUKE_ATTEMPT_ACTION,
            {"reason": "bad_phrase", "scope": "user", "targetUserId": user_id},
        )
        raise HTTPException(
            status_code=400, detail=f"Type '{CONFIRMATION_PHRASE_USER_NUKE}' exactly to confirm."
        )
    if body.password != body.confirm_password:
        await log_action(
            current_user.id,
            NUKE_ATTEMPT_ACTION,
            {"reason": "password_mismatch", "scope": "user", "targetUserId": user_id},
        )
        raise HTTPException(status_code=400, detail="Password and confirmation do not match.")

    admin = await db.users.find_one({"_id": current_user.id})
    if admin is None or not verify_password(body.password, admin["passwordHash"]):
        await log_action(
            current_user.id,
            NUKE_ATTEMPT_ACTION,
            {"reason": "bad_password", "scope": "user", "targetUserId": user_id},
        )
        raise HTTPException(status_code=400, detail="Incorrect password.")

    query = _build_range_filter(target_id, body.older_than_months, body.year, body.month)
    deleted_count = await _nuke_documents(db, query)
    await log_action(
        current_user.id,
        NUKE_ATTEMPT_ACTION,
        {
            "reason": "success",
            "scope": "user",
            "targetUserId": user_id,
            "deletedCount": deleted_count,
        },
    )
    return {
        "message": f"Deleted {deleted_count} documents for this user.",
        "deletedCount": deleted_count,
    }


@router.post("/nuke-global")
async def nuke_global(
    body: AdminNukeRequest, current_user: CurrentUser = Depends(require_admin)
) -> dict[str, Any]:
    """Bulk-deletes documents across ALL users (age-based or Year+Month). Same double-
    password/phrase/rate-limit protections as nuke_user, scoped globally instead of to one
    user - see that route's docstring."""
    db = get_database()
    await _enforce_nuke_rate_limit(db, current_user.id)

    if body.confirmation_phrase != CONFIRMATION_PHRASE_GLOBAL_NUKE:
        await log_action(
            current_user.id, NUKE_ATTEMPT_ACTION, {"reason": "bad_phrase", "scope": "global"}
        )
        raise HTTPException(
            status_code=400, detail=f"Type '{CONFIRMATION_PHRASE_GLOBAL_NUKE}' exactly to confirm."
        )
    if body.password != body.confirm_password:
        await log_action(
            current_user.id,
            NUKE_ATTEMPT_ACTION,
            {"reason": "password_mismatch", "scope": "global"},
        )
        raise HTTPException(status_code=400, detail="Password and confirmation do not match.")

    admin = await db.users.find_one({"_id": current_user.id})
    if admin is None or not verify_password(body.password, admin["passwordHash"]):
        await log_action(
            current_user.id, NUKE_ATTEMPT_ACTION, {"reason": "bad_password", "scope": "global"}
        )
        raise HTTPException(status_code=400, detail="Incorrect password.")

    query = _build_range_filter(None, body.older_than_months, body.year, body.month)
    deleted_count = await _nuke_documents(db, query)
    await log_action(
        current_user.id,
        NUKE_ATTEMPT_ACTION,
        {"reason": "success", "scope": "global", "deletedCount": deleted_count},
    )
    return {
        "message": f"Deleted {deleted_count} documents across all users.",
        "deletedCount": deleted_count,
    }


@router.get("/documents", response_model=ListResponse)
async def list_all_documents(
    user_id: str | None = Query(None, alias="userId"),
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
    current_user: CurrentUser = Depends(require_admin),
) -> ListResponse:
    db = get_database()
    query: dict[str, Any] = {}
    if user_id:
        if not is_valid_object_id(user_id):
            raise HTTPException(status_code=400, detail="Invalid user id.")
        query["userId"] = ObjectId(user_id)

    total = await db.documents.count_documents(query)
    cursor = db.documents.find(query).sort("createdAt", -1).skip((page - 1) * limit).limit(limit)
    docs = await cursor.to_list(length=limit)

    owner_ids = {doc["userId"] for doc in docs}
    owners = {u["_id"]: u async for u in db.users.find({"_id": {"$in": list(owner_ids)}})}
    items = [_serialize_document(doc, owners.get(doc["userId"])) for doc in docs]
    return ListResponse(items=items, total=total, page=page, limit=limit)


async def _get_any_document(document_id: str) -> dict[str, Any]:
    if not is_valid_object_id(document_id):
        raise HTTPException(status_code=400, detail="Invalid document id.")
    db = get_database()
    doc = await db.documents.find_one({"_id": ObjectId(document_id)})
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc


@router.get("/documents/{document_id}")
async def admin_get_document(
    document_id: str, current_user: CurrentUser = Depends(require_admin)
) -> dict[str, Any]:
    db = get_database()
    doc = await _get_any_document(document_id)
    owner = await db.users.find_one({"_id": doc["userId"]})
    return _serialize_document(doc, owner)


@router.patch("/documents/{document_id}")
async def admin_correct_document(
    document_id: str, body: CorrectRequest, current_user: CurrentUser = Depends(require_admin)
) -> dict[str, str]:
    db = get_database()
    doc = await _get_any_document(document_id)
    await apply_field_correction(
        db, doc, body.field, body.value, actor_user_id=current_user.id, by_admin=True
    )
    return {"message": "Field updated."}


@router.delete("/documents/{document_id}")
async def admin_delete_document(
    document_id: str, current_user: CurrentUser = Depends(require_admin)
) -> dict[str, str]:
    """Permanently deletes the document record and its original files - see
    documents/router.py's delete_document for the file-deletion-never-blocks-record-removal
    rationale, identical here."""
    db = get_database()
    doc = await _get_any_document(document_id)
    await _best_effort_purge_files(doc)
    await db.documents.delete_one({"_id": doc["_id"]})
    await db.corrections.delete_many({"documentId": doc["_id"]})
    await log_action(
        current_user.id, "document_deleted", {"documentId": document_id, "byAdmin": True}
    )
    return {"message": "Document permanently deleted."}


@router.post("/documents/{document_id}/purge-files")
async def admin_purge_document_files(
    document_id: str, current_user: CurrentUser = Depends(require_admin)
) -> dict[str, str]:
    db = get_database()
    doc = await _get_any_document(document_id)
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

    await log_action(
        current_user.id, "document_file_purged", {"documentId": document_id, "byAdmin": True}
    )
    return {"message": "Original files purged. Extracted data was preserved."}


@router.get("/logs", response_model=ListResponse)
async def list_logs(
    action: str | None = Query(None),
    user_id: str | None = Query(None, alias="userId"),
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
    current_user: CurrentUser = Depends(require_admin),
) -> ListResponse:
    db = get_database()
    query: dict[str, Any] = {}
    if action:
        query["action"] = action
    if user_id:
        if not is_valid_object_id(user_id):
            raise HTTPException(status_code=400, detail="Invalid user id.")
        query["userId"] = ObjectId(user_id)

    total = await db.auditlogs.count_documents(query)
    cursor = db.auditlogs.find(query).sort("createdAt", -1).skip((page - 1) * limit).limit(limit)
    logs = await cursor.to_list(length=limit)

    owner_ids = {log["userId"] for log in logs if log.get("userId")}
    owners = {u["_id"]: u async for u in db.users.find({"_id": {"$in": list(owner_ids)}})}
    items = []
    for log in logs:
        entry = dict(log)
        entry["id"] = str(entry.pop("_id"))
        owner = owners.get(entry.get("userId"))
        entry["userId"] = str(entry["userId"]) if entry.get("userId") else None
        entry["username"] = owner["username"] if owner else None
        items.append(entry)
    return ListResponse(items=items, total=total, page=page, limit=limit)


@router.get("/telemetry", response_model=TelemetryResponse)
async def telemetry(current_user: CurrentUser = Depends(require_admin)) -> TelemetryResponse:
    db = get_database()
    total_users = await db.users.count_documents({})
    total_documents = await db.documents.count_documents({})

    status_counts: dict[str, int] = {}
    for status in ("uploaded", "processing", "processed", "failed"):
        status_counts[status] = await db.documents.count_documents({"uploadStatus": status})

    low_confidence = await db.documents.count_documents({"hasLowConfidenceFields": True})
    multi_page = await db.documents.count_documents({"multiPage": True})

    processed = status_counts["processed"]
    failed = status_counts["failed"]
    failure_rate = failed / (processed + failed) if (processed + failed) > 0 else 0.0

    now = datetime.now(UTC)
    last_24h = await db.auditlogs.count_documents(
        {"createdAt": {"$gte": now - timedelta(hours=24)}}
    )
    last_7d = await db.auditlogs.count_documents({"createdAt": {"$gte": now - timedelta(days=7)}})

    return TelemetryResponse(
        total_users=total_users,
        total_documents=total_documents,
        documents_by_status=status_counts,
        documents_with_low_confidence=low_confidence,
        multi_page_documents=multi_page,
        ocr_failure_rate=round(failure_rate, 4),
        recent_activity_last_24_hours=last_24h,
        recent_activity_last_7_days=last_7d,
    )


@router.get("/orphaned-files", response_model=ListResponse)
async def list_orphaned_files(
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
    current_user: CurrentUser = Depends(require_admin),
) -> ListResponse:
    db = get_database()
    total = await db.orphanedfiles.count_documents({})
    cursor = (
        db.orphanedfiles.find({}).sort("lastAttemptAt", -1).skip((page - 1) * limit).limit(limit)
    )
    items = [_serialize_orphan(record) async for record in cursor]
    return ListResponse(items=items, total=total, page=page, limit=limit)


async def _get_orphan_record(record_id: str) -> dict[str, Any]:
    if not is_valid_object_id(record_id):
        raise HTTPException(status_code=400, detail="Invalid orphaned file record id.")
    db = get_database()
    record = await db.orphanedfiles.find_one({"_id": ObjectId(record_id)})
    if record is None:
        raise HTTPException(status_code=404, detail="Orphaned file record not found.")
    return record


@router.post("/orphaned-files/{record_id}/retry")
async def retry_orphaned_file(
    record_id: str, current_user: CurrentUser = Depends(require_admin)
) -> dict[str, str]:
    """Re-attempts the GridFS delete for one orphan record. Success removes the record;
    failure updates it in place (record_orphan upserts by fileId) and reports the error back
    to the admin rather than swallowing it - the whole point of this route is visibility."""
    db = get_database()
    record = await _get_orphan_record(record_id)
    try:
        await delete_file(record["fileId"])
    except Exception as exc:  # noqa: BLE001 - reported to the admin, not swallowed
        await record_orphan(record["fileId"], record.get("documentId"), record.get("userId"), exc)
        await log_action(
            current_user.id,
            "orphaned_file_retry_failed",
            {"fileId": str(record["fileId"]), "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail=f"Retry failed: {exc}") from exc

    await db.orphanedfiles.delete_one({"_id": record["_id"]})
    await log_action(
        current_user.id, "orphaned_file_retry_succeeded", {"fileId": str(record["fileId"])}
    )
    return {"message": "File deleted; orphan record cleared."}


@router.delete("/orphaned-files/{record_id}")
async def dismiss_orphaned_file(
    record_id: str, current_user: CurrentUser = Depends(require_admin)
) -> dict[str, str]:
    db = get_database()
    record = await _get_orphan_record(record_id)
    await db.orphanedfiles.delete_one({"_id": record["_id"]})
    await log_action(current_user.id, "orphaned_file_dismissed", {"fileId": str(record["fileId"])})
    return {"message": "Orphaned file record dismissed."}
