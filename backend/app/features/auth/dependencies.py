"""Auth dependencies — role/tokenVersion are re-read from the DB, never trusted from the JWT."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.database import get_database
from app.core.security import decode_token

_bearer = HTTPBearer(auto_error=False)

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
PENDING_MESSAGE = "Waiting for admin approval."
REJECTED_MESSAGE = "Your request was not approved. Contact the admin."
REVOKED_MESSAGE = "Your access was removed. Contact the admin."


def iso_utc(value: Any) -> str | None:
    """A datetime (naive = UTC) as an ISO UTC string; anything else -> None."""
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def raise_if_not_approved(user: dict[str, Any]) -> None:
    """403 with a structured detail for a pending / rejected / revoked account. A missing
    status field is a legacy account and counts as approved; an unknown status fails closed
    as rejected. Old rejected users have no `decision` and are reported as rejected."""
    user_status = user.get("status", STATUS_APPROVED)
    if user_status == STATUS_APPROVED:
        return
    if user_status == STATUS_PENDING:
        code, message = "ACCOUNT_PENDING", PENDING_MESSAGE
    elif user.get("decision") == "revoked":
        code, message = "ACCOUNT_REVOKED", REVOKED_MESSAGE
    else:
        code, message = "ACCOUNT_REJECTED", REJECTED_MESSAGE
    raise HTTPException(
        status_code=403,
        detail={
            "code": code,
            "message": message,
            "reason": user.get("decisionReason") or None,
            "requestedAt": iso_utc(user.get("createdAt")),
            "decidedAt": iso_utc(user.get("decidedAt")),
        },
    )


@dataclass
class CurrentUser:
    id: ObjectId
    username: str
    email: str
    role: str
    token_version: int
    must_change_password: bool = False


# Sent with a 403 to a user holding an admin-set temporary password (ACKN's shape).
PASSWORD_CHANGE_REQUIRED = {
    "code": "PASSWORD_CHANGE_REQUIRED",
    "message": "You must set a new password before continuing.",
}


async def _authenticate(credentials: HTTPAuthorizationCredentials | None) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = payload.get("userId")
    if not user_id or not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=401, detail="Invalid token")

    db = get_database()
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    # Single enforcement point for the admin-approval gate: every protected route depends
    # on this function, so a pending/rejected account is locked out everywhere, even with
    # an old token. A missing status field is a pre-approval-era account and stays approved.
    # Checked BEFORE the tokenVersion comparison so a rejected user's old (revoked) token still
    # gets the clear 403 "not approved" message instead of a generic 401. This leaks nothing:
    # the token's signature was already verified above, so only the account's own holder gets here.
    raise_if_not_approved(user)

    if user.get("tokenVersion", 0) != payload.get("tokenVersion"):
        raise HTTPException(status_code=401, detail="Session expired, please log in again")

    return CurrentUser(
        id=user["_id"],
        username=user["username"],
        email=user["email"],
        role=user.get("role", "user"),
        token_version=user.get("tokenVersion", 0),
        must_change_password=user.get("mustChangePassword") is True,
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    """Every protected route. Also the single enforcement point of the forced password change:
    a user holding an admin-set temporary password gets 403 PASSWORD_CHANGE_REQUIRED everywhere
    (require_admin included) except the two routes using the variant below."""
    user = await _authenticate(credentials)
    if user.must_change_password:
        raise HTTPException(status_code=403, detail=PASSWORD_CHANGE_REQUIRED)
    return user


async def get_current_user_allow_password_change(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    """Same checks, but lets a flagged user through. ONLY GET /auth/me and
    POST /auth/change-password may depend on this."""
    return await _authenticate(credentials)


async def require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return current_user
