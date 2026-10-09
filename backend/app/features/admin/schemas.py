"""Request/response schemas for admin routes."""

from typing import Any

from pydantic import Field

from app.core.base_model import CamelModel


class UpdateUserRequest(CamelModel):
    username: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=254)
    role: str | None = Field(default=None, max_length=16)


class AdminNukeRequest(CamelModel):
    """Body for both /users/{id}/nuke (user-scoped) and /nuke-global. Exactly one of
    older_than_months or year must be set; month is optional and only valid alongside year
    (Year+Month mode) - see _build_range_filter for the exact validation."""

    password: str = Field(max_length=128)
    confirm_password: str = Field(max_length=128)
    confirmation_phrase: str = Field(max_length=64)
    older_than_months: int | None = None
    year: int | None = None
    month: int | None = None


class ListResponse(CamelModel):
    items: list[dict[str, Any]]
    total: int
    page: int
    limit: int


class UserListResponse(ListResponse):
    # Drives the badge on the admin panel's Pending tab.
    pending_count: int


class TelemetryResponse(CamelModel):
    total_users: int
    total_documents: int
    documents_by_status: dict[str, int]
    documents_with_low_confidence: int
    multi_page_documents: int
    ocr_failure_rate: float
    recent_activity_last_24_hours: int
    recent_activity_last_7_days: int
