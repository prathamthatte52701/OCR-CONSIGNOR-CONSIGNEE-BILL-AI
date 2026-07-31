"""Request/response schemas for admin routes."""

from typing import Any

from app.core.base_model import CamelModel


class UpdateUserRequest(CamelModel):
    username: str | None = None
    email: str | None = None
    role: str | None = None


class ListResponse(CamelModel):
    items: list[dict[str, Any]]
    total: int
    page: int
    limit: int


class TelemetryResponse(CamelModel):
    total_users: int
    total_documents: int
    documents_by_status: dict[str, int]
    documents_with_low_confidence: int
    multi_page_documents: int
    ocr_failure_rate: float
    recent_activity_last_24_hours: int
    recent_activity_last_7_days: int
