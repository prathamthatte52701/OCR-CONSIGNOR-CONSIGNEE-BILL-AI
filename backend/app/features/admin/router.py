"""Admin routes: every route behind require_admin. Cross-user CRUD on users/documents,
telemetry, audit log viewer, and bulk "nuke" deletion (per-user or global, age-based or
Year+Month, double-password + rate-limited - see nuke_user/nuke_global). Role is always
re-verified server-side via require_admin's DB lookup - never trusted from a JWT claim."""

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from gridfs.errors import NoFile
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.core.audit_log import log_action
from app.core.database import get_database
from app.core.filenames import attachment_header
from app.core.object_id import is_valid_object_id
from app.core.orphaned_files import record_orphan
from app.core.security import verify_password
from app.core.validators import is_valid_email, is_valid_username, normalize_email
from app.features.admin.schemas import (
    AdminNukeRequest,
    ListResponse,
    TelemetryResponse,
    UpdateUserRequest,
    UserListResponse,
)
from app.features.auth.dependencies import (
    STATUS_APPROVED,
    STATUS_REJECTED,
    CurrentUser,
    require_admin,
)
from app.features.documents.correction_service import apply_field_correction
from app.features.documents.gridfs_service import delete_file, download_buffer
from app.features.documents.schemas import CorrectRequest

router = APIRouter()

NUKE_ATTEMPT_ACTION = "admin_nuke_attempt"
NUKE_RATE_LIMIT_WINDOW_HOURS = 24
NUKE_RATE_LIMIT_MAX_ATTEMPTS = 5
ADMIN_VIEWED_DOCUMENT = "admin_viewed_document"
ADMIN_DOWNLOADED_PART1 = "admin_downloaded_part1"
ADMIN_DOWNLOADED_PART2 = "admin_downloaded_part2"
CONFIRMATION_PHRASE_USER_NUKE = "NUKE USER"
CONFIRMATION_PHRASE_GLOBAL_NUKE = "NUKE ALL"


def _serialize_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(user["_id"]),
        "username": user["username"],
        "email": user["email"],
        "role": user.get("role", "user"),
        "status": user.get("status", STATUS_APPROVED),
        "createdAt": user.get("createdAt"),
        "updatedAt": user.get("updatedAt"),
    }


def _status_query(status: str) -> dict[str, Any]:
    # A user document with no status field is a pre-approval-era account and counts as
    # approved everywhere.
    if status == STATUS_APPROVED:
        return {"$or": [{"status": STATUS_APPROVED}, {"status": {"$exists": False}}]}
    return {"status": status}


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


@router.get("/users", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
    status: Literal["pending", "approved", "rejected"] | None = Query(default=None),
    current_user: CurrentUser = Depends(require_admin),
) -> UserListResponse:
    db = get_database()
    query = _status_query(status) if status else {}
    total = await db.users.count_documents(query)
    cursor = (
        db.users.find(query, {"passwordHash": 0})
        .sort("createdAt", -1)
        .skip((page - 1) * limit)
        .limit(limit)
    )
    items = [_serialize_user(user) async for user in cursor]
    pending_count = await db.users.count_documents(_status_query("pending"))
    return UserListResponse(
        items=items, total=total, page=page, limit=limit, pending_count=pending_count
    )


async def _set_user_status(user_id: str, new_status: str, admin: CurrentUser) -> dict[str, Any]:
    if not is_valid_object_id(user_id):
        raise HTTPException(status_code=400, detail="Invalid user id.")
    db = get_database()
    target_id = ObjectId(user_id)
    user = await db.users.find_one({"_id": target_id})
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    update: dict[str, Any] = {"$set": {"status": new_status, "updatedAt": datetime.now(UTC)}}
    if new_status == STATUS_REJECTED:
        # Admins (including yourself) can never be locked out this way.
        if user.get("role") == "admin":
            raise HTTPException(status_code=400, detail="Admin accounts cannot be rejected.")
        if target_id == admin.id:
            raise HTTPException(status_code=400, detail="You cannot reject your own account.")
        # Bumping tokenVersion kills every token already issued to this user.
        update["$inc"] = {"tokenVersion": 1}
    await db.users.update_one({"_id": target_id}, update)
    await log_action(
        admin.id,
        "user_approved" if new_status == STATUS_APPROVED else "user_rejected",
        {
            "targetUserId": user_id,
            "targetEmail": user["email"],
            "previous": user.get("status", STATUS_APPROVED),
        },
    )
    refreshed = await db.users.find_one({"_id": target_id})
    assert refreshed is not None
    return _serialize_user(refreshed)


@router.post("/users/{user_id}/approve")
async def approve_user(
    user_id: str, current_user: CurrentUser = Depends(require_admin)
) -> dict[str, Any]:
    return await _set_user_status(user_id, STATUS_APPROVED, current_user)


@router.post("/users/{user_id}/reject")
async def reject_user(
    user_id: str, current_user: CurrentUser = Depends(require_admin)
) -> dict[str, Any]:
    """Reject a pending request OR revoke an approved user - same action: the account is
    locked out and every issued token dies (tokenVersion bump)."""
    return await _set_user_status(user_id, STATUS_REJECTED, current_user)


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
    audit: dict[str, Any] = {"userId": user_id}
    email_changed = False
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
        if normalized_email != user["email"]:
            taken = await db.users.find_one(
                {"email": normalized_email, "_id": {"$ne": user["_id"]}}
            )
            if taken is not None:
                raise HTTPException(status_code=400, detail="That email is already in use.")
            updates["email"] = normalized_email
            audit.update({"previousEmail": user["email"], "newEmail": normalized_email})
            email_changed = True
    if body.role is not None:
        if body.role not in ("user", "admin"):
            raise HTTPException(status_code=400, detail="Role must be 'user' or 'admin'.")
        updates["role"] = body.role

    if updates:
        updates["updatedAt"] = datetime.now(UTC)
        update: dict[str, Any] = {"$set": updates}
        if email_changed:
            # The email is the login identity: bumping tokenVersion logs the user out
            # everywhere, so no session keeps running under the old address.
            update["$inc"] = {"tokenVersion": 1}
        try:
            await db.users.update_one({"_id": user["_id"]}, update)
        except DuplicateKeyError:  # lost a race against another signup / edit
            raise HTTPException(status_code=400, detail="That email is already in use.") from None
        audit["fields"] = [k for k in updates if k != "updatedAt"]
        await log_action(current_user.id, "user_updated", audit)

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


async def _log_admin_access(admin: CurrentUser, doc: dict[str, Any], action: str) -> None:
    """Audit trail for an admin OPENING someone else's document (detail view or a file).
    Written BEFORE any data is returned, so a failed audit write fails the request instead of
    letting the access go unrecorded. Looking at your own document is not logged."""
    if doc["userId"] == admin.id:
        return
    await log_action(
        admin.id,
        action,
        {"targetUserId": str(doc["userId"]), "documentId": str(doc["_id"])},
    )


@router.get("/documents/{document_id}")
async def admin_get_document(
    document_id: str, current_user: CurrentUser = Depends(require_admin)
) -> dict[str, Any]:
    db = get_database()
    doc = await _get_any_document(document_id)
    await _log_admin_access(current_user, doc, ADMIN_VIEWED_DOCUMENT)
    owner = await db.users.find_one({"_id": doc["userId"]})
    return _serialize_document(doc, owner)


async def _admin_file_response(
    admin: CurrentUser, document_id: str, part: Literal["part1", "part2"]
) -> Response:
    doc = await _get_any_document(document_id)
    label = "Part 1" if part == "part1" else "Part 2"
    file_id = doc.get(f"{part}GridFsFileId")
    if doc.get(f"{part}FilePurged"):
        raise HTTPException(status_code=400, detail=f"{label} file has been purged.")
    if not file_id:
        raise HTTPException(status_code=404, detail=f"{label} file not found.")
    try:
        data = await download_buffer(file_id)
    except NoFile:
        raise HTTPException(status_code=404, detail=f"{label} file not found.") from None
    await _log_admin_access(
        admin, doc, ADMIN_DOWNLOADED_PART1 if part == "part1" else ADMIN_DOWNLOADED_PART2
    )
    return Response(
        content=data,
        media_type=doc.get(f"{part}MimeType") or "application/octet-stream",
        headers=attachment_header(doc.get(f"{part}OriginalFilename"), part),
    )


@router.get("/documents/{document_id}/download/part1")
async def admin_download_part1(
    document_id: str, current_user: CurrentUser = Depends(require_admin)
) -> Response:
    return await _admin_file_response(current_user, document_id, "part1")


@router.get("/documents/{document_id}/download/part2")
async def admin_download_part2(
    document_id: str, current_user: CurrentUser = Depends(require_admin)
) -> Response:
    return await _admin_file_response(current_user, document_id, "part2")


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
