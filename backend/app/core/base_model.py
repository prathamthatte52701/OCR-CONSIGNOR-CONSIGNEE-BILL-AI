"""Shared Pydantic base: Python stays snake_case, wire/DB format is camelCase."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.core.object_id import PyObjectId


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )


class MongoBaseModel(CamelModel):
    id: PyObjectId | None = Field(default=None, alias="_id")
    created_at: datetime | None = None
    updated_at: datetime | None = None
