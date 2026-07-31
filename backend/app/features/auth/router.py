"""Auth routes: signup (no auto-login), login, profile, change-password, forgot-password."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pymongo.errors import DuplicateKeyError

from app.core.audit_log import log_action
from app.core.database import get_database
from app.core.rate_limit import check_login_email_limit, limiter
from app.core.security import hash_password, sign_token, verify_password
from app.core.validators import (
    is_valid_email,
    is_valid_password,
    is_valid_username,
    normalize_email,
)
from app.features.auth.dependencies import CurrentUser, get_current_user
from app.features.auth.schemas import (
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
PASSWORD_RULE_ERROR = (
    "Password must be 8-32 chars with upper, lower, number, special char, and no whitespace."
)


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
    if not is_valid_password(body.password):
        raise HTTPException(
            status_code=400,
            detail=PASSWORD_RULE_ERROR,
        )

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
                "tokenVersion": 0,
                "createdAt": now,
                "updatedAt": now,
            }
        )
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail=GENERIC_SIGNUP_ERROR) from None

    await log_action(None, "signup", {"email": email})
    return {"message": "Account created. Please log in."}


@router.post("/login", response_model=AuthResponse)
@limiter.limit("100/15minute")
async def login(request: Request, body: LoginRequest) -> AuthResponse:
    email = normalize_email(body.email)

    if not check_login_email_limit(email):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")

    db = get_database()
    user = await db.users.find_one({"email": email})
    if user is None or not verify_password(body.password, user["passwordHash"]):
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

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
    updates: dict[str, str] = {}
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

    db = get_database()
    if updates:
        updates["updatedAt"] = datetime.now(UTC)  # type: ignore[assignment]
        try:
            await db.users.update_one({"_id": current_user.id}, {"$set": updates})
        except DuplicateKeyError:
            raise HTTPException(status_code=400, detail="Email already in use.") from None

    user = await db.users.find_one({"_id": current_user.id})
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return MeResponse(
        id=str(user["_id"]),
        username=user["username"],
        email=user["email"],
        role=user.get("role", "user"),
    )


@router.post("/change-password", response_model=AuthResponse)
@limiter.limit("20/15minute")
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> AuthResponse:
    if not is_valid_password(body.new_password):
        raise HTTPException(
            status_code=400,
            detail=PASSWORD_RULE_ERROR,
        )

    db = get_database()
    user = await db.users.find_one({"_id": current_user.id})
    if user is None or not verify_password(body.current_password, user["passwordHash"]):
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
    if not is_valid_password(body.new_password):
        raise HTTPException(
            status_code=400,
            detail=PASSWORD_RULE_ERROR,
        )

    db = get_database()
    email = normalize_email(body.email)
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
