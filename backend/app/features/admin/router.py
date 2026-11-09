"""Admin routes: every route behind require_admin. Cross-user CRUD on users/documents,
telemetry, audit log viewer, and bulk "nuke" deletion (per-user or global, age-based or
Year+Month, double-password + rate-limited - see nuke_user/nuke_global). Role is always
re-verified server-side via require_admin's DB lookup - never trusted from a JWT claim."""

import logging
import re
import time
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
from app.core.object_id import PyObjectId, is_valid_object_id
from app.core.orphaned_files import record_orphan
from app.core.security import hash_password, verify_password
from app.core.validators import is_valid_email, is_valid_username, normalize_email, password_problem
from app.features.admin.dashboard import (
    document_telemetry,
    gather_untyped,
    recent_feed,
    series_days,
    trend,
)
from app.features.admin.schemas import (
    AdminNukeRequest,
    EmailChangeRequest,
    ListResponse,
    PurgeMonthsRequest,
    RejectRequest,
    TelemetryResponse,
    TempPasswordRequest,
    UpdateUserRequest,
    UserListResponse,
)
from app.features.auth.dependencies import (
    STATUS_APPROVED,
    STATUS_REJECTED,
    CurrentUser,
    require_admin,
)
from app.features.chat.files import count_files as chat_count_files
from app.features.chat.files import delete_attachments as chat_delete_attachments
from app.features.documents.correction_service import apply_field_correction
from app.features.documents.file_purge import (
    DELETE_FAILED_MESSAGE,
    DELETE_OK_MESSAGE,
    PURGE_FAILED_MESSAGE,
    PURGE_OK_MESSAGE,
    best_effort_purge_files,
    document_snapshot,
    purge_parts,
)
from app.features.documents.gridfs_service import delete_file, download_buffer
from app.features.documents.schemas import CorrectRequest

logger = logging.getLogger(__name__)
router = APIRouter()

NUKE_ATTEMPT_ACTION = "admin_nuke_attempt"
NUKE_RATE_LIMIT_WINDOW_HOURS = 24
NUKE_RATE_LIMIT_MAX_ATTEMPTS = 5
ADMIN_VIEWED_DOCUMENT = "admin_viewed_document"
ADMIN_DOWNLOADED_PART1 = "admin_downloaded_part1"
ADMIN_DOWNLOADED_PART2 = "admin_downloaded_part2"
CONFIRMATION_PHRASE_USER_NUKE = "NUKE USER"
CONFIRMATION_PHRASE_GLOBAL_NUKE = "NUKE ALL"
PURGE_MONTH_CHOICES = (1, 2, 3, 6, 9)
_STARTED_AT = time.monotonic()


def _serialize_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(user["_id"]),
        "username": user["username"],
        "email": user["email"],
        "role": user.get("role", "user"),
        "status": user.get("status", STATUS_APPROVED),
        "decision": user.get("decision"),
        "decidedAt": user.get("decidedAt"),
        "decisionReason": user.get("decisionReason"),
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
        await best_effort_purge_files(doc)
    doc_ids = [doc["_id"] for doc in docs]
    result = await db.documents.delete_many(query)
    if doc_ids:
        await db.corrections.delete_many({"documentId": {"$in": doc_ids}})
        # Audit rows keep a name snapshot for one-by-one deletes; a nuke must not leave it.
        # No index on context.documentId: a rare admin action, so a scan is acceptable.
        try:
            id_strings = [str(i) for i in doc_ids]
            for start in range(0, len(id_strings), 500):
                await db.auditlogs.update_many(
                    {"context.documentId": {"$in": id_strings[start : start + 500]}},
                    {"$unset": {"context.invoiceNo": "", "context.consignee": ""}},
                )
        except Exception as exc:  # noqa: BLE001 - the scrub must not fail the nuke
            logger.error("nuke audit scrub failed: class=%s", type(exc).__name__)
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


def _guard_other_admin(target: dict[str, Any], admin: CurrentUser) -> None:
    """An admin may not act on another admin's account; only that admin can."""
    if target.get("role") == "admin" and target["_id"] != admin.id:
        raise HTTPException(status_code=403, detail="Only that admin can change their own account.")


async def _set_user_status(
    user_id: str, new_status: str, admin: CurrentUser, reason: str | None = None
) -> dict[str, Any]:
    if not is_valid_object_id(user_id):
        raise HTTPException(status_code=400, detail="Invalid user id.")
    db = get_database()
    target_id = ObjectId(user_id)
    user = await db.users.find_one({"_id": target_id})
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    _guard_other_admin(user, admin)
    now = datetime.now(UTC)
    previous = user.get("status", STATUS_APPROVED)
    update: dict[str, Any] = {"$set": {"status": new_status, "updatedAt": now, "decidedAt": now}}
    decision_audit: dict[str, Any] = {}
    if new_status == STATUS_APPROVED:
        update["$set"]["decision"] = "approved"
        update["$set"]["decisionReason"] = None
        if previous != STATUS_APPROVED:  # the welcome notice is only for someone who was waiting
            update["$set"]["approvalNoticePending"] = True
    else:
        # approved before (or already revoked) = revoked; a pending request = rejected
        revoked = previous == STATUS_APPROVED or (
            previous == STATUS_REJECTED and user.get("decision") == "revoked"
        )
        update["$set"]["approvalNoticePending"] = False
        if previous == STATUS_REJECTED:
            # rejecting again keeps the first decision and date; only a NEW reason replaces
            del update["$set"]["decidedAt"]
            if reason is not None:
                update["$set"]["decisionReason"] = reason
            decision_audit = {"decision": user.get("decision"), "reason": reason}
        else:
            update["$set"]["decision"] = "revoked" if revoked else "rejected"
            update["$set"]["decisionReason"] = reason
            decision_audit = {"decision": update["$set"]["decision"], "reason": reason}
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
            "previous": previous,
            **decision_audit,
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
    user_id: str,
    body: RejectRequest | None = None,
    current_user: CurrentUser = Depends(require_admin),
) -> dict[str, Any]:
    """Reject a pending request OR revoke an approved user - same action: the account is
    locked out and every issued token dies (tokenVersion bump). The optional reason is
    plain text (trimmed; empty = none)."""
    reason = ((body.reason if body else None) or "").strip() or None
    return await _set_user_status(user_id, STATUS_REJECTED, current_user, reason)


def _serialize_password_request(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(r["_id"]),
        "userId": str(r["userId"]),
        "username": r.get("username"),
        "email": r.get("email"),
        "note": r.get("note") or "",
        "status": r["status"],
        "createdAt": r.get("createdAt"),
        "updatedAt": r.get("updatedAt"),
        "resolvedAt": r.get("resolvedAt"),
        "resolution": r.get("resolution"),
    }


@router.get("/password-requests")
async def list_password_requests(
    status: Literal["open", "all"] = Query(default="open"),
    current_user: CurrentUser = Depends(require_admin),
) -> dict[str, Any]:
    db = get_database()
    query = {"status": "open"} if status == "open" else {}
    rows = await db.passwordresetrequests.find(query).sort("createdAt", -1).limit(500).to_list(500)
    rows.sort(key=lambda r: r["status"] != "open")  # stable: open first, newest first inside
    open_count = await db.passwordresetrequests.count_documents({"status": "open"})
    return {"requests": [_serialize_password_request(r) for r in rows], "openCount": open_count}


async def _open_request_or_error(db: AsyncIOMotorDatabase, request_id: ObjectId) -> dict[str, Any]:
    req = await db.passwordresetrequests.find_one({"_id": request_id})
    if not req:
        raise HTTPException(status_code=404, detail="Request not found.")
    if req["status"] != "open":
        raise HTTPException(status_code=409, detail="This request has already been handled.")
    return req


@router.post("/password-requests/{request_id}/temp-password")
async def set_temp_password(
    request_id: PyObjectId,
    body: TempPasswordRequest,
    current_user: CurrentUser = Depends(require_admin),
) -> dict[str, bool]:
    """The app sends no email: the admin tells the user the temporary password personally.
    The user must choose a new one at the next login (mustChangePassword)."""
    db = get_database()
    req = await _open_request_or_error(db, request_id)
    user = await db.users.find_one({"_id": req["userId"]})
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    _guard_other_admin(user, current_user)
    if user.get("role") == "admin" or user.get("status", STATUS_APPROVED) != STATUS_APPROVED:
        raise HTTPException(
            status_code=403, detail="A temporary password can only be set for an approved user."
        )
    if (
        problem := password_problem(body.password, user.get("username"), user.get("email"))
    ) is not None:
        raise HTTPException(status_code=422, detail=problem)

    new_hash = hash_password(body.password)  # slow: before claiming anything
    now = datetime.now(UTC)
    # 1) claim the request atomically (a second admin loses with 409)
    claimed = await db.passwordresetrequests.find_one_and_update(
        {"_id": request_id, "status": "open"},
        {
            "$set": {
                "status": "done",
                "resolution": "temp_password",
                "resolvedAt": now,
                "resolvedBy": current_user.id,
                "updatedAt": now,
            }
        },
    )
    if claimed is None:
        raise HTTPException(status_code=409, detail="This request has already been handled.")

    async def roll_back() -> None:
        try:
            await db.passwordresetrequests.update_one(
                {"_id": request_id, "status": "done", "resolvedAt": now},
                {
                    "$set": {
                        "status": "open",
                        "resolution": None,
                        "resolvedAt": None,
                        "resolvedBy": None,
                    }
                },
            )
        except DuplicateKeyError:
            pass  # the user filed a fresh open request meanwhile; that one is the live request

    # 2) update the user, only if still an approved non-admin
    try:
        result = await db.users.update_one(
            {"_id": req["userId"], "role": {"$ne": "admin"}, **_status_query(STATUS_APPROVED)},
            {
                "$set": {"passwordHash": new_hash, "mustChangePassword": True, "updatedAt": now},
                "$inc": {"tokenVersion": 1},
            },
        )
    except Exception:
        await roll_back()
        raise
    # 3) nothing matched: undo the claim
    if result.matched_count == 0:
        await roll_back()
        raise HTTPException(
            status_code=403, detail="A temporary password can only be set for an approved user."
        )
    # 4) audit (ids only, never the password)
    await log_action(
        current_user.id,
        "password_reset_temp_set",
        {"targetUserId": str(req["userId"]), "requestId": str(request_id)},
    )
    return {"ok": True}


@router.post("/password-requests/{request_id}/dismiss")
async def dismiss_password_request(
    request_id: PyObjectId, current_user: CurrentUser = Depends(require_admin)
) -> dict[str, bool]:
    db = get_database()
    req = await _open_request_or_error(db, request_id)
    now = datetime.now(UTC)
    result = await db.passwordresetrequests.update_one(
        {"_id": request_id, "status": "open"},
        {
            "$set": {
                "status": "dismissed",
                "resolution": "dismissed",
                "resolvedAt": now,
                "resolvedBy": current_user.id,
                "updatedAt": now,
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=409, detail="This request has already been handled.")
    await log_action(
        current_user.id,
        "password_reset_dismissed",
        {"targetUserId": str(req["userId"]), "requestId": str(request_id)},
    )
    return {"ok": True}


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
    _guard_other_admin(user, current_user)

    updates: dict[str, Any] = {}
    audit: dict[str, Any] = {"userId": user_id}
    if body.username is not None:
        if not is_valid_username(body.username):
            raise HTTPException(
                status_code=400, detail="Username must be 3-8 characters, no whitespace."
            )
        updates["username"] = body.username
    if body.email is not None:
        raise HTTPException(status_code=400, detail="Use the change-email action.")
    if body.role is not None:
        if user["_id"] == current_user.id and body.role != "admin":
            raise HTTPException(status_code=400, detail="You cannot remove your own admin role.")
        if body.role not in ("user", "admin"):
            raise HTTPException(status_code=400, detail="Role must be 'user' or 'admin'.")
        updates["role"] = body.role

    if updates:
        updates["updatedAt"] = datetime.now(UTC)
        await db.users.update_one({"_id": user["_id"]}, {"$set": updates})
        audit["fields"] = [k for k in updates if k != "updatedAt"]
        await log_action(current_user.id, "user_updated", audit)

    updated = await db.users.find_one({"_id": user["_id"]})
    assert updated is not None
    return _serialize_user(updated)


@router.put("/users/{user_id}/email")
async def change_user_email(
    user_id: str, body: EmailChangeRequest, current_user: CurrentUser = Depends(require_admin)
) -> dict[str, Any]:
    """Changes a user's login email. Signs the user out everywhere (tokenVersion bump) and
    leaves a one-time notice for their next login. Never touches a password."""
    if not is_valid_object_id(user_id):
        raise HTTPException(status_code=400, detail="Invalid user id.")
    if user_id == str(current_user.id):
        raise HTTPException(status_code=400, detail="You cannot change your own email here.")
    db = get_database()
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    _guard_other_admin(user, current_user)

    email = normalize_email(body.email)
    if not is_valid_email(email):
        raise HTTPException(status_code=400, detail="Invalid email address.")
    if email == str(user["email"]).lower():
        raise HTTPException(status_code=400, detail="That is already this user's email.")
    taken = await db.users.find_one(
        {
            "email": {"$regex": f"^{re.escape(email)}$", "$options": "i"},
            "_id": {"$ne": user["_id"]},
        }
    )
    if taken is not None:
        raise HTTPException(status_code=400, detail="That email is already in use.")

    try:
        await db.users.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "email": email,
                    "updatedAt": datetime.now(UTC),
                    "emailChangeNoticePending": True,
                },
                "$inc": {"tokenVersion": 1},
            },
        )
    except DuplicateKeyError:  # lost a race against another signup / edit
        raise HTTPException(status_code=400, detail="That email is already in use.") from None
    # Keep the open password-reset request pointing at the new address (this user only).
    await db.passwordresetrequests.update_one(
        {"userId": user["_id"], "status": "open"}, {"$set": {"email": email}}
    )
    # One row on the user (My Activity) and one on the admin; ids and addresses only.
    await log_action(
        user["_id"],
        "email_changed_by_admin",
        {"byAdmin": True, "adminId": str(current_user.id), "newEmail": email},
    )
    await log_action(current_user.id, "admin_changed_user_email", {"userId": user_id})
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
    _guard_other_admin(user, current_user)

    docs = await db.documents.find({"userId": target_id}).to_list(length=None)
    for doc in docs:
        await best_effort_purge_files(doc)
    await db.documents.delete_many({"userId": target_id})
    await db.corrections.delete_many({"userId": target_id})
    await db.auditlogs.delete_many({"userId": target_id})
    chat_files = await chat_delete_attachments(db, {"threadUserId": target_id})
    await db.chatmessages.delete_many({"threadUserId": target_id})  # only this user's thread
    await db.users.delete_one({"_id": target_id})
    await db.chatmessages.delete_many({"threadUserId": target_id})  # a message sent during delete
    late = await chat_delete_attachments(db, {"threadUserId": target_id})
    chat_files = {k: chat_files[k] + late[k] for k in chat_files}

    await log_action(
        current_user.id,
        "user_deleted",
        {
            "userId": user_id,
            "chatFilesDeleted": chat_files["files"],
            "chatBytesFreed": chat_files["bytes"],
        },
    )
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
    _guard_other_admin(target, current_user)

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


def _purge_query(months: int, user_id: ObjectId | None) -> dict[str, Any]:
    if months not in PURGE_MONTH_CHOICES:
        raise HTTPException(
            status_code=400,
            detail=f"months must be one of {', '.join(str(m) for m in PURGE_MONTH_CHOICES)}.",
        )
    query: dict[str, Any] = {"createdAt": {"$lt": datetime.now(UTC) - timedelta(days=30 * months)}}
    if user_id is not None:  # per-user purge is scoped by userId and nothing else
        query["userId"] = user_id
    return query


async def _purge_preview(db: AsyncIOMotorDatabase, query: dict[str, Any]) -> dict[str, int]:
    """Dry run: how many documents match and how many stored bytes would be freed."""

    def size(part: str) -> dict[str, Any]:
        return {
            "$cond": [{"$ne": [f"${part}FilePurged", True]}, {"$ifNull": [f"${part}Size", 0]}, 0]
        }

    rows = await db.documents.aggregate(
        [
            {"$match": query},
            {
                "$group": {
                    "_id": None,
                    "documents": {"$sum": 1},
                    "bytes": {"$sum": {"$add": [size("part1"), size("part2")]}},
                }
            },
        ]
    ).to_list(length=1)
    row = rows[0] if rows else {}
    return {"documents": row.get("documents", 0), "bytes": row.get("bytes", 0)}


async def _check_purge_gate(
    db: AsyncIOMotorDatabase,
    admin_id: ObjectId,
    body: PurgeMonthsRequest,
    phrase: str,
    scope: dict[str, Any],
) -> None:
    """The same gate as nuke_user / nuke_global: shared rate limit, exact phrase, password
    typed twice, then the admin's own password. Every refusal is logged as a nuke attempt."""
    await _enforce_nuke_rate_limit(db, admin_id)
    refusal: tuple[str, str] | None = None
    if body.confirmation_phrase != phrase:
        refusal = ("bad_phrase", f"Type '{phrase}' exactly to confirm.")
    elif body.password != body.confirm_password:
        refusal = ("password_mismatch", "Password and confirmation do not match.")
    else:
        admin = await db.users.find_one({"_id": admin_id})
        if admin is None or not verify_password(body.password, admin["passwordHash"]):
            refusal = ("bad_password", "Incorrect password.")
    if refusal is not None:
        await log_action(admin_id, NUKE_ATTEMPT_ACTION, {"reason": refusal[0], **scope})
        raise HTTPException(status_code=400, detail=refusal[1])


async def _run_purge(
    db: AsyncIOMotorDatabase, admin_id: ObjectId, query: dict[str, Any], scope: dict[str, Any]
) -> dict[str, Any]:
    freed = (await _purge_preview(db, query))["bytes"]
    deleted_count = await _nuke_documents(db, query)
    # One audit entry per purge, counts only.
    await log_action(
        admin_id,
        NUKE_ATTEMPT_ACTION,
        {"reason": "success", **scope, "deletedCount": deleted_count, "bytes": freed},
    )
    return {
        "message": f"Deleted {deleted_count} documents older than {scope['months']} months.",
        "deletedCount": deleted_count,
        "bytes": freed,
    }


@router.get("/purge-months/preview")
async def preview_purge_months(
    months: int = Query(...),
    user_id: str | None = Query(None, alias="userId"),
    current_user: CurrentUser = Depends(require_admin),
) -> dict[str, int]:
    """Dry-run count for either purge: add userId for the per-user one."""
    if user_id is not None and not is_valid_object_id(user_id):
        raise HTTPException(status_code=400, detail="Invalid user id.")
    query = _purge_query(months, ObjectId(user_id) if user_id else None)
    return {"months": months, **await _purge_preview(get_database(), query)}


@router.delete("/users/{user_id}/purge-months")
async def purge_user_months(
    user_id: str,
    body: PurgeMonthsRequest,
    months: int = Query(...),
    current_user: CurrentUser = Depends(require_admin),
) -> dict[str, Any]:
    """Deletes one user's documents older than `months` (1, 2, 3, 6 or 9), oldest included,
    with the full nuke gate. Scoped by userId only."""
    if not is_valid_object_id(user_id):
        raise HTTPException(status_code=400, detail="Invalid user id.")
    query = _purge_query(months, ObjectId(user_id))
    db = get_database()
    target = await db.users.find_one({"_id": ObjectId(user_id)})
    if target is None:
        raise HTTPException(status_code=404, detail="User not found.")
    _guard_other_admin(target, current_user)
    scope = {"scope": "user", "purge": "months", "months": months, "targetUserId": user_id}
    await _check_purge_gate(db, current_user.id, body, CONFIRMATION_PHRASE_USER_NUKE, scope)
    return await _run_purge(db, current_user.id, query, scope)


@router.delete("/purge-months")
async def purge_global_months(
    body: PurgeMonthsRequest,
    months: int = Query(...),
    current_user: CurrentUser = Depends(require_admin),
) -> dict[str, Any]:
    """Global version of purge_user_months. Touches documents only: never users, admins or
    the audit log."""
    query = _purge_query(months, None)
    db = get_database()
    scope = {"scope": "global", "purge": "months", "months": months}
    await _check_purge_gate(db, current_user.id, body, CONFIRMATION_PHRASE_GLOBAL_NUKE, scope)
    return await _run_purge(db, current_user.id, query, scope)


@router.get("/system")
async def system_info(current_user: CurrentUser = Depends(require_admin)) -> dict[str, Any]:
    """Read-only health and storage numbers. No hostnames, URIs or settings."""
    db = get_database()
    started = time.perf_counter()
    try:
        await db.command("ping")
        db_ok = True
    except Exception:  # noqa: BLE001 - a dead database is a result here, not an error
        db_ok = False
    ping_ms = round((time.perf_counter() - started) * 1000, 1)

    rows = (
        await db["fs.files"]
        .aggregate([{"$group": {"_id": None, "files": {"$sum": 1}, "bytes": {"$sum": "$length"}}}])
        .to_list(length=1)
    )
    storage = rows[0] if rows else {}
    return {
        "db": {"ok": db_ok, "pingMs": ping_ms},
        "uptimeSeconds": int(time.monotonic() - _STARTED_AT),
        "storage": {"files": storage.get("files", 0), "bytes": storage.get("bytes", 0)},
        "documentsProcessed": await db.documents.count_documents({"uploadStatus": "processed"}),
        "documentsTotal": await db.documents.count_documents({}),
        "orphanedFiles": await db.orphanedfiles.count_documents({}),
        # the same figure the chat storage cap uses (non-expired attachments); counts only
        "chat": await chat_count_files(db, {}),
    }


MAINTENANCE_ACTIONS = [
    NUKE_ATTEMPT_ACTION,
    "document_deleted",
    "document_file_purged",
    "orphaned_file_dismissed",
    "orphaned_file_retry_succeeded",
    "orphaned_file_retry_failed",
    "user_deleted",
    "chat_cleared",
    "chat_clear_blocked",
]
# Chat rows show counts and the reason only: no text, no names, no user ids.
CHAT_CONTEXT_KEYS = ("range", "deleted", "files", "bytes", "reason")
MAINTENANCE_CONTEXT_KEYS = (
    "reason",
    "scope",
    "purge",
    "months",
    "deletedCount",
    "bytes",
    "documentId",
    "userId",
    "targetUserId",
    "byAdmin",
)


@router.get("/maintenance-activity")
async def maintenance_activity(
    limit: int = Query(30, ge=1, le=100), current_user: CurrentUser = Depends(require_admin)
) -> dict[str, Any]:
    """Recent deletes, purges, orphan actions and nukes from the audit log (a refused nuke
    attempt shows too)."""
    db = get_database()
    logs = (
        await db.auditlogs.find({"action": {"$in": MAINTENANCE_ACTIONS}})
        .sort([("createdAt", -1), ("_id", -1)])
        .limit(limit)
        .to_list(length=limit)
    )
    admin_ids = list({log["userId"] for log in logs if log.get("userId")})
    names = {u["_id"]: u["username"] async for u in db.users.find({"_id": {"$in": admin_ids}})}
    items = []
    for log in logs:
        ctx = log.get("context") if isinstance(log.get("context"), dict) else {}
        if log["action"].startswith("chat_"):
            shown = {k: ctx[k] for k in CHAT_CONTEXT_KEYS if k in ctx}
            if "scope" in ctx:
                shown["scope"] = "all" if ctx["scope"] == "all" else "user"
            ctx = shown
        items.append(
            {
                "id": str(log["_id"]),
                "action": log["action"],
                "by": names.get(log.get("userId")),
                "context": {
                    k: ctx[k] for k in (*MAINTENANCE_CONTEXT_KEYS, *CHAT_CONTEXT_KEYS) if k in ctx
                },
                "createdAt": log.get("createdAt"),
            }
        )
    return {"items": items}


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
) -> dict[str, Any]:
    """Permanently deletes the document record and its original files - see
    documents/router.py's delete_document for the file-deletion-never-blocks-record-removal
    rationale, identical here."""
    db = get_database()
    doc = await _get_any_document(document_id)
    cleanup_failed = await best_effort_purge_files(doc)
    await db.documents.delete_one({"_id": doc["_id"]})
    await db.corrections.delete_many({"documentId": doc["_id"]})
    await log_action(
        current_user.id,
        "document_deleted",
        {"documentId": document_id, "byAdmin": True, **document_snapshot(doc)},
    )
    message = DELETE_FAILED_MESSAGE if cleanup_failed else DELETE_OK_MESSAGE
    return {"message": message, "gridFsCleanupFailed": cleanup_failed}


@router.post("/documents/{document_id}/purge-files")
async def admin_purge_document_files(
    document_id: str, current_user: CurrentUser = Depends(require_admin)
) -> dict[str, Any]:
    db = get_database()
    doc = await _get_any_document(document_id)
    updates, cleanup_failed = await purge_parts(doc, datetime.now(UTC))
    if updates:
        updates["updatedAt"] = datetime.now(UTC)
        await db.documents.update_one({"_id": doc["_id"]}, {"$set": updates})

    await log_action(
        current_user.id,
        "document_file_purged",
        {"documentId": document_id, "byAdmin": True, **document_snapshot(doc)},
    )
    message = PURGE_FAILED_MESSAGE if cleanup_failed else PURGE_OK_MESSAGE
    return {"message": message, "gridFsCleanupFailed": cleanup_failed}


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
    cursor = (
        db.auditlogs.find(query)
        .sort([("createdAt", -1), ("_id", -1)])
        .skip((page - 1) * limit)
        .limit(limit)
    )
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

    days = series_days()
    pending = _status_query("pending")
    (
        doc_stats,
        users_trend,
        pending_count,
        pending_rows,
        orphaned,
        open_requests,
        feed,
    ) = await gather_untyped(
        document_telemetry(db, days),
        trend(db, "users", "createdAt"),
        db.users.count_documents(pending),
        db.users.find(pending, {"username": 1, "email": 1, "createdAt": 1})
        .sort("createdAt", 1)
        .limit(5)
        .to_list(5),
        db.orphanedfiles.count_documents({}),
        db.passwordresetrequests.count_documents({"status": "open"}),
        recent_feed(db),
    )

    return TelemetryResponse(
        failed_documents=failed,
        orphaned_files=orphaned,
        password_requests={"count": open_requests},
        series={
            "days": days,
            "uploads": doc_stats["uploads"],
            "failures": doc_stats["failures"],
        },
        trends={
            "users": users_trend,
            "uploads": doc_stats["uploads_trend"],
            "failures": doc_stats["failures_trend"],
        },
        processed_documents={"total": processed, **doc_stats["processed_trend"]},
        pending_users={
            "count": pending_count,
            "oldest": [
                {
                    "id": str(u["_id"]),
                    "username": u["username"],
                    "email": u["email"],
                    "createdAt": u.get("createdAt"),
                }
                for u in pending_rows
            ],
        },
        activity_feed=feed,
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
