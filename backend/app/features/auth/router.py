"""Auth routes: signup (no auto-login), login, profile, change-password, password-reset request."""

from datetime import UTC, datetime
from typing import Any, Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pymongo.errors import DuplicateKeyError

from app.core.audit_log import log_action
from app.core.database import get_database
from app.core.object_id import is_valid_object_id
from app.core.rate_limit import check_login_email_limit, check_reset_email_limit, limiter
from app.core.security import DUMMY_PASSWORD_HASH, hash_password, sign_token, verify_password
from app.core.validators import (
    MAX_EMAIL_LENGTH,
    is_valid_email,
    is_valid_username,
    normalize_email,
    password_problem,
)
from app.features.auth.dependencies import (
    STATUS_PENDING,
    CurrentUser,
    get_current_user,
    get_current_user_allow_password_change,
    iso_utc,
    raise_if_not_approved,
)
from app.features.auth.password_requests import (
    GENERIC_RESET_MESSAGE,
    can_request_reset,
    handle_reset_request,
    sanitize_note,
)
from app.features.auth.schemas import (
    ActivityListResponse,
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    MeResponse,
    PasswordResetRequestBody,
    SignupRequest,
    UpdateMeRequest,
)

router = APIRouter()

GENERIC_SIGNUP_ERROR = "Unable to create account. Please try a different username or email."
GENERIC_LOGIN_ERROR = "Invalid email or password."


def _reject_bad_password(password: str, username: str | None, email: str | None) -> None:
    """400 with the first problem found (length in bytes, character rules, blocklist, own
    username/email). Only for NEW passwords - never called on login."""
    if (problem := password_problem(password, username, email)) is not None:
        raise HTTPException(status_code=400, detail=problem)


@router.post("/signup", status_code=201)
@limiter.limit("15/hour")
async def signup(request: Request, body: SignupRequest) -> dict[str, str]:
    email = normalize_email(body.email)

    if not is_valid_username(body.username):
        raise HTTPException(
            status_code=400, detail="Username must be 3-8 characters, no whitespace."
        )
    if not is_valid_email(email):
        raise HTTPException(status_code=400, detail="Invalid email address.")
    _reject_bad_password(body.password, body.username, email)

    db = get_database()

    # Hash before the uniqueness check to avoid a timing side-channel on email enumeration.
    password_hash = hash_password(body.password)

    existing = await db.users.find_one({"email": email})
    if existing is not None:
        raise HTTPException(status_code=400, detail=GENERIC_SIGNUP_ERROR)

    now = datetime.now(UTC)
    try:
        await db.users.insert_one(
            {
                "username": body.username,
                "email": email,
                "passwordHash": password_hash,
                "role": "user",
                "status": STATUS_PENDING,
                "tokenVersion": 0,
                "createdAt": now,
                "updatedAt": now,
            }
        )
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail=GENERIC_SIGNUP_ERROR) from None

    await log_action(None, "signup", {"email": email})
    return {"message": "Account created. Waiting for admin approval."}


@router.post("/login", response_model=AuthResponse)
@limiter.limit("100/15minute")
async def login(request: Request, body: LoginRequest) -> AuthResponse:
    email = normalize_email(body.email)
    if len(email) > MAX_EMAIL_LENGTH:
        # Can never match an account; same answer as a wrong password, and the limiter and
        # database never see the over-long key.
        verify_password(body.password, DUMMY_PASSWORD_HASH)
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

    if not check_login_email_limit(email):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")

    db = get_database()
    user = await db.users.find_one({"email": email})
    # Always exactly one bcrypt check (against a dummy hash when there is no usable password)
    # so unknown email / no-password account / wrong password are indistinguishable in both
    # the response and the timing.
    stored_hash = user.get("passwordHash") if user else None
    password_ok = verify_password(body.password, stored_hash or DUMMY_PASSWORD_HASH)
    if user is None or not stored_hash or not password_ok:
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)
    # Checked only AFTER the password is proven, so the pending/rejected message is never
    # shown to someone who doesn't own the account (no status oracle).
    raise_if_not_approved(user)

    # Auto-close an open password-reset request: the user got in with their own password.
    # Skipped while a temporary password is in force (that request is already done). One
    # conditional update, so it is race-safe and a no-op when nothing is open.
    if user.get("mustChangePassword") is not True:
        now = datetime.now(UTC)
        await db.passwordresetrequests.update_one(
            {"userId": user["_id"], "status": "open"},
            {
                "$set": {
                    "status": "done",
                    "resolution": "user_logged_in",
                    "resolvedAt": now,
                    "resolvedBy": None,
                    "updatedAt": now,
                }
            },
        )

    # One-time "you were approved" notice: claimed atomically AFTER the password and the
    # approval gate, so only one concurrent login gets it and a failed login never uses it.
    claimed = await db.users.find_one_and_update(
        {"_id": user["_id"], "approvalNoticePending": True},
        {"$set": {"approvalNoticePending": False}},
    )
    # One-time "your email was changed by an admin" notice, claimed the same way.
    email_notice = await db.users.find_one_and_update(
        {"_id": user["_id"], "emailChangeNoticePending": True},
        {"$set": {"emailChangeNoticePending": False}},
    )
    token = sign_token(str(user["_id"]), user.get("tokenVersion", 0), user.get("role", "user"))
    await log_action(user["_id"], "login", {})
    return AuthResponse(
        token=token,
        username=user["username"],
        email=user["email"],
        role=user.get("role", "user"),
        just_approved=claimed is not None,
        email_changed=email_notice is not None,
        approved_at=iso_utc(claimed.get("decidedAt")) if claimed else None,
    )


@router.get("/me", response_model=MeResponse)
async def get_me(
    current_user: CurrentUser = Depends(get_current_user_allow_password_change),
) -> MeResponse:
    return MeResponse(
        id=str(current_user.id),
        username=current_user.username,
        email=current_user.email,
        role=current_user.role,
    )


@router.patch("/me", response_model=MeResponse)
async def update_me(
    body: UpdateMeRequest, current_user: CurrentUser = Depends(get_current_user)
) -> MeResponse:
    # Email is the login identity and the approval anchor, so only an admin may change it
    # (admin panel -> PATCH /api/admin/users/{id}). Re-sending the unchanged address is
    # harmless and allowed (the profile form does). Checked FIRST so nothing is half-applied.
    if body.email is not None and normalize_email(body.email) != current_user.email:
        raise HTTPException(
            status_code=403, detail="Only an admin can change your email. Contact the admin."
        )

    updates: dict[str, Any] = {}
    if body.username is not None:
        if not is_valid_username(body.username):
            raise HTTPException(
                status_code=400, detail="Username must be 3-8 characters, no whitespace."
            )
        updates["username"] = body.username

    db = get_database()
    if updates:
        updates["updatedAt"] = datetime.now(UTC)
        await db.users.update_one({"_id": current_user.id}, {"$set": updates})

    user = await db.users.find_one({"_id": current_user.id})
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return MeResponse(
        id=str(user["_id"]),
        username=user["username"],
        email=user["email"],
        role=user.get("role", "user"),
    )


DOCUMENT_ACTIONS = [
    "document_uploaded",
    "document_reprocessed",
    "document_deleted",
    "document_file_purged",
    "document_corrected",
    "documents_download_all",
]
ACCOUNT_ACTIONS = [
    "login",
    "password_change",
    "password_reset_requested",
    "email_changed_by_admin",
]
ACTIVITY_CONTEXT_KEYS = (
    "documentId",
    "field",
    "invoiceNo",
    "consignee",
    "requested",
    "included",
    "skipped",
    "byAdmin",
)


@router.get("/me/activity", response_model=ActivityListResponse)
async def get_my_activity(
    type: Literal["all", "documents", "account"] = Query("all"),
    page: int = Query(1, ge=1),
    limit: int = Query(40, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
) -> ActivityListResponse:
    db = get_database()
    actions = {
        "all": DOCUMENT_ACTIONS + ACCOUNT_ACTIONS,
        "documents": DOCUMENT_ACTIONS,
        "account": ACCOUNT_ACTIONS,
    }[type]
    query = {"userId": current_user.id, "action": {"$in": actions}}

    total = await db.auditlogs.count_documents(query)
    cursor = (
        db.auditlogs.find(query)
        .sort([("createdAt", -1), ("_id", -1)])
        .skip((page - 1) * limit)
        .limit(limit)
    )
    logs = await cursor.to_list(length=limit)

    # One lookup for every document named on this page; userId is mandatory (no cross-user leak).
    doc_ids = {
        ObjectId(str(log["context"]["documentId"]))
        for log in logs
        if isinstance(log.get("context"), dict)
        and is_valid_object_id(str(log["context"].get("documentId", "")))
    }
    found: dict[str, dict[str, Any]] = {}
    if doc_ids:
        rows = db.documents.find(
            {"_id": {"$in": list(doc_ids)}, "userId": current_user.id},
            {"invoiceNo": 1, "consigneeCode": 1, "consignee": 1},
        )
        found = {str(r["_id"]): r async for r in rows}

    items = []
    for log in logs:
        ctx = log.get("context") if isinstance(log.get("context"), dict) else {}
        row = found.get(str(ctx.get("documentId", "")))
        items.append(
            {
                "id": str(log["_id"]),
                "action": log["action"],
                "context": {
                    k: ctx[k]
                    for k in ACTIVITY_CONTEXT_KEYS
                    if k in ctx and (k != "byAdmin" or isinstance(ctx[k], bool))
                },
                "createdAt": log.get("createdAt"),
                "document": (
                    None
                    if row is None
                    else {
                        "id": str(row["_id"]),
                        "invoiceNo": row.get("invoiceNo"),
                        "consigneeCode": row.get("consigneeCode"),
                        "consignee": row.get("consignee"),
                    }
                ),
            }
        )
    return ActivityListResponse(items=items, total=total, page=page, limit=limit)


@router.post("/change-password", response_model=AuthResponse)
@limiter.limit("20/15minute")
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    current_user: CurrentUser = Depends(get_current_user_allow_password_change),
) -> AuthResponse:
    _reject_bad_password(body.new_password, current_user.username, current_user.email)

    db = get_database()
    user = await db.users.find_one({"_id": current_user.id})
    stored_hash = user.get("passwordHash") if user else None
    if user is None or not stored_hash or not verify_password(body.current_password, stored_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    was_forced = user.get("mustChangePassword") is True
    if was_forced and body.new_password == body.current_password:
        raise HTTPException(
            status_code=400, detail="New password must be different from the temporary one."
        )

    new_token_version = user.get("tokenVersion", 0) + 1
    update: dict[str, Any] = {
        "$set": {
            "passwordHash": hash_password(body.new_password),
            "tokenVersion": new_token_version,
            "updatedAt": datetime.now(UTC),
        }
    }
    if was_forced:
        update["$unset"] = {"mustChangePassword": ""}
    # Conditional on the hash + tokenVersion verified above: if an admin set a temporary password
    # in between, that write wins and this one is refused instead of overwriting it.
    written = await db.users.update_one(
        {
            "_id": current_user.id,
            "passwordHash": stored_hash,
            "tokenVersion": user.get("tokenVersion", 0),
        },
        update,
    )
    if written.matched_count == 0:
        raise HTTPException(
            status_code=409, detail="Your password was changed elsewhere. Please log in again."
        )
    await log_action(current_user.id, "password_change", {})
    if was_forced:
        # A request filed between the temporary password and this change would stay open.
        closed_at = datetime.now(UTC)
        await db.passwordresetrequests.update_one(
            {"userId": current_user.id, "status": "open"},
            {
                "$set": {
                    "status": "done",
                    "resolution": "user_logged_in",
                    "resolvedAt": closed_at,
                    "resolvedBy": None,
                    "updatedAt": closed_at,
                }
            },
        )

    # Re-issue a token for the current session so this tab stays logged in;
    # every other outstanding token dies because its tokenVersion no longer matches.
    token = sign_token(str(current_user.id), new_token_version, current_user.role)
    return AuthResponse(
        token=token, username=user["username"], email=user["email"], role=current_user.role
    )


@router.post("/password-reset-request")
@limiter.limit("10/hour")
async def password_reset_request(
    request: Request, body: PasswordResetRequestBody
) -> dict[str, str]:
    """Public. Always the same generic 200 (only the limits can answer 429, and the per-email
    limit counts every email, existing or not); a request row is created only for an approved,
    non-admin account with a password."""
    email = normalize_email(body.email)
    if not check_reset_email_limit(email):
        raise HTTPException(
            status_code=429, detail="Too many requests for this address. Try again later."
        )
    db = get_database()
    user = await db.users.find_one({"email": email})
    await handle_reset_request(db, user, sanitize_note(body.note), can_request_reset(user))
    return {"message": GENERIC_RESET_MESSAGE}
