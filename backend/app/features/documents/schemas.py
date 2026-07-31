"""Request/response schemas for document routes."""

from typing import Any

from app.core.base_model import CamelModel


class DocumentListResponse(CamelModel):
    items: list[dict[str, Any]]
    total: int
    page: int
    limit: int


class UploadResponse(CamelModel):
    id: str
    upload_status: str


class CorrectRequest(CamelModel):
    field: str
    value: str | None = None


class PurgeAllRequest(CamelModel):
    password: str
    confirmation_phrase: str


class PurgeRangeRequest(CamelModel):
    password: str
    confirmation_phrase: str
    older_than_months: int | None = None
    year: int | None = None


class StatsResponse(CamelModel):
    total: int
    processed: int
    failed: int
    processed_today: int
    low_confidence: int
    multi_page: int
