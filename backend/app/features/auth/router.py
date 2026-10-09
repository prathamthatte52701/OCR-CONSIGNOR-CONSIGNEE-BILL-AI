"""Auth routes: signup (no auto-login), login, profile, change-password, forgot-password."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pymongo.errors import DuplicateKeyError

from app.core.audit_log import log_action
from app.core.database import get_database
from app.core.rate_limit import check_login_email_limit, limiter
from app.core.security import DUMMY_PASSWORD_HASH, hash_password, sign_token, verify_password
from app.core.validators import (
    is_valid_email,
    is_valid_username,
    normalize_email,
    password_problem,
)
from app.features.auth.dependencies import (
    STATUS_APPROVED,
    STATUS_PENDING,
    CurrentUser,
    get_current_user,
    raise_if_not_approved,
)
from app.features.auth.schemas import (
    ActivityListResponse,
    AuthResponse,
    ChangePasswordRequest,
    ForgotPasswordResetRequest,
    ForgotPasswordVerifyRequest,
    LoginRequest,
    MeResponse,
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
    raise_if_not_approved(user.get("status", STATUS_APPROVED))

    token = sign_token(str(user["_id"]), user.get("tokenVersion", 0), user.get("role", "user"))
    await log_action(user["_id"], "login", {})
    return AuthResponse(
        token=token, username=user["username"], email=user["email"], role=user.get("role", "user")
    )


@router.get("/me", response_model=MeResponse)
async def get_me(current_user: CurrentUser = Depends(get_current_user)) -> MeResponse:
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


@router.get("/me/activity", response_model=ActivityListResponse)
async def get_my_activity(
    page: int = Query(1, ge=1),
    limit: int = Query(40, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
) -> ActivityListResponse:
    db = get_database()
    query = {"userId": current_user.id}

    total = await db.auditlogs.count_documents(query)
    cursor = db.auditlogs.find(query).sort("createdAt", -1).skip((page - 1) * limit).limit(limit)
    logs = await cursor.to_list(length=limit)

    items = []
    for log in logs:
        entry = dict(log)
        entry["id"] = str(entry.pop("_id"))
        entry["userId"] = str(entry["userId"]) if entry.get("userId") else None
        items.append(entry)
    return ActivityListResponse(items=items, total=total, page=page, limit=limit)


@router.post("/change-password", response_model=AuthResponse)
@limiter.limit("20/15minute")
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> AuthResponse:
    _reject_bad_password(body.new_password, current_user.username, current_user.email)

    db = get_database()
    user = await db.users.find_one({"_id": current_user.id})
    stored_hash = user.get("passwordHash") if user else None
    if user is None or not stored_hash or not verify_password(body.current_password, stored_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    new_token_version = user.get("tokenVersion", 0) + 1
    await db.users.update_one(
        {"_id": current_user.id},
        {
            "$set": {
                "passwordHash": hash_password(body.new_password),
                "tokenVersion": new_token_version,
                "updatedAt": datetime.now(UTC),
            }
        },
    )
    await log_action(current_user.id, "password_change", {})

    # Re-issue a token for the current session so this tab stays logged in;
    # every other outstanding token dies because its tokenVersion no longer matches.
    token = sign_token(str(current_user.id), new_token_version, current_user.role)
    return AuthResponse(
        token=token, username=user["username"], email=user["email"], role=current_user.role
    )


@router.post("/forgot-password/verify")
@limiter.limit("20/15minute")
async def forgot_password_verify(
    request: Request, body: ForgotPasswordVerifyRequest
) -> dict[str, bool]:
    db = get_database()
    email = normalize_email(body.email)
    user = await db.users.find_one({"username": body.username, "email": email})
    if user is None:
        raise HTTPException(status_code=400, detail="Username and email do not match any account.")
    return {"verified": True}


@router.post("/forgot-password/reset")
@limiter.limit("20/15minute")
async def forgot_password_reset(
    request: Request, body: ForgotPasswordResetRequest
) -> dict[str, str]:
    email = normalize_email(body.email)
    _reject_bad_password(body.new_password, body.username, email)

    db = get_database()
    user = await db.users.find_one({"username": body.username, "email": email})
    if user is None:
        raise HTTPException(status_code=400, detail="Username and email do not match any account.")

    await db.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "passwordHash": hash_password(body.new_password),
                "tokenVersion": user.get("tokenVersion", 0) + 1,
                "updatedAt": datetime.now(UTC),
            }
        },
    )
    await log_action(user["_id"], "password_reset", {})
    return {"message": "Password reset. Please log in with your new password."}
