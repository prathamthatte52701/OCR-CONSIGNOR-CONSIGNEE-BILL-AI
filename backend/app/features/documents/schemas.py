"""Request/response schemas for document routes."""

from typing import Any

from pydantic import Field

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
    field: str = Field(max_length=64)
    value: str | None = Field(default=None, max_length=2000)


class StatsResponse(CamelModel):
    total: int
    processed: int
    failed: int
    processed_today: int
    low_confidence: int
    multi_page: int
    needs_review: int = 0
    processing: int = 0
    corrected: int = 0


class StorageResponse(CamelModel):
    documents: int
    bytes: int


class DownloadAllRequest(CamelModel):
    document_ids: list[str] = Field(default_factory=list, max_length=500)
