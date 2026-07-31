"""Admin routes: every route behind require_admin. Cross-user CRUD on users/documents,
telemetry, audit log viewer. Role is always re-verified server-side via require_admin's
DB lookup - never trusted from a JWT claim."""

from datetime import UTC, datetime, timedelta
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.audit_log import log_action
from app.core.database import get_database
from app.core.object_id import is_valid_object_id
from app.core.validators import is_valid_email, is_valid_username, normalize_email
from app.features.admin.schemas import ListResponse, TelemetryResponse, UpdateUserRequest
from app.features.auth.dependencies import CurrentUser, require_admin
from app.features.documents.correction_service import apply_field_correction
from app.features.documents.gridfs_service import delete_file
from app.features.documents.schemas import CorrectRequest

router = APIRouter()


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


async def _best_effort_purge_files(doc: dict[str, Any]) -> None:
    for key in ("part1GridFsFileId", "part2GridFsFileId"):
        file_id = doc.get(key)
        if file_id:
            try:
                await delete_file(file_id)
            except Exception:  # noqa: BLE001 - best-effort, never blocks the delete
                pass


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
    db = get_database()
    doc = await _get_any_document(document_id)
    now = datetime.now(UTC)
    await db.documents.update_one(
        {"_id": doc["_id"]}, {"$set": {"isDeleted": True, "deletedAt": now, "updatedAt": now}}
    )
    await _best_effort_purge_files(doc)
    await log_action(
        current_user.id, "document_deleted", {"documentId": document_id, "byAdmin": True}
    )
    return {"message": "Document deleted."}


@router.post("/documents/{document_id}/purge-files")
async def admin_purge_document_files(
    document_id: str, current_user: CurrentUser = Depends(require_admin)
) -> dict[str, str]:
    db = get_database()
    doc = await _get_any_document(document_id)
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
    total_documents = await db.documents.count_documents({"isDeleted": False})

    status_counts: dict[str, int] = {}
    for status in ("uploaded", "processing", "processed", "failed"):
        status_counts[status] = await db.documents.count_documents(
            {"isDeleted": False, "uploadStatus": status}
        )

    low_confidence = await db.documents.count_documents(
        {"isDeleted": False, "hasLowConfidenceFields": True}
    )
    multi_page = await db.documents.count_documents({"isDeleted": False, "multiPage": True})

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
