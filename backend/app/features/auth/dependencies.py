"""Auth dependencies — role/tokenVersion are re-read from the DB, never trusted from the JWT."""

from dataclasses import dataclass

from bson import ObjectId
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.database import get_database
from app.core.security import decode_token

_bearer = HTTPBearer(auto_error=False)


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
