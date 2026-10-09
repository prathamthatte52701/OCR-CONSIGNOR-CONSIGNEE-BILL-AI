"""Auth dependencies — role/tokenVersion are re-read from the DB, never trusted from the JWT."""

from dataclasses import dataclass

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


def raise_if_not_approved(user_status: str) -> None:
    if user_status == STATUS_PENDING:
        raise HTTPException(status_code=403, detail=PENDING_MESSAGE)
    if user_status != STATUS_APPROVED:
        raise HTTPException(status_code=403, detail=REJECTED_MESSAGE)


@dataclass
class CurrentUser:
    id: ObjectId
    username: str
    email: str
    role: str
    token_version: int


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
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
    raise_if_not_approved(user.get("status", STATUS_APPROVED))

    if user.get("tokenVersion", 0) != payload.get("tokenVersion"):
        raise HTTPException(status_code=401, detail="Session expired, please log in again")

    return CurrentUser(
        id=user["_id"],
        username=user["username"],
        email=user["email"],
        role=user.get("role", "user"),
        token_version=user.get("tokenVersion", 0),
    )


async def require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return current_user
