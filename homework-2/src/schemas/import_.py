from uuid import UUID

from pydantic import BaseModel, Field


class ImportItemError(BaseModel):
    row: int
    error: str


class ImportSummary(BaseModel):
    total: int
    successful: int
    failed: int
    errors: list[ImportItemError] = Field(default_factory=list)
    created_ids: list[UUID] = Field(default_factory=list)
