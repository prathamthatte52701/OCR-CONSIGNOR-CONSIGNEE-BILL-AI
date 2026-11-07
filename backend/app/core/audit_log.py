"""Single helper for writing audit log rows — called from every mutating route."""

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from loguru import logger

from app.core.database import get_database


async def log_action(
    user_id: ObjectId | None, action: str, context: dict[str, Any] | None = None
) -> None:
    db = get_database()
    await db.auditlogs.insert_one(
        {
            "userId": user_id,
            "action": action,
            "context": context or {},
            "createdAt": datetime.now(UTC),
        }
    )


async def safe_log_action(
    user_id: ObjectId | None, action: str, context: dict[str, Any] | None = None
) -> None:
    """log_action that can never break the caller: a logging failure is only logged."""
    try:
        await log_action(user_id, action, context)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Audit log '{action}' failed: class={type(exc).__name__}")
