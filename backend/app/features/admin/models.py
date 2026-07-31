"""Audit log model - inserts are written via app.core.audit_log.log_action."""

from typing import Any

from bson import ObjectId

from app.core.base_model import MongoBaseModel


class AuditLog(MongoBaseModel):
    user_id: ObjectId | None
    action: str
    context: dict[str, Any] = {}
