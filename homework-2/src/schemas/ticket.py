from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.models.enums import Category, DeviceType, Priority, Source, Status


class TicketMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source: Source | None = None
    browser: str | None = None
    device_type: DeviceType | None = None


class TicketBase(BaseModel):
    customer_id: Annotated[str, Field(min_length=1, max_length=255)]
    customer_email: EmailStr
    customer_name: Annotated[str, Field(min_length=1, max_length=255)]
    subject: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(min_length=10, max_length=2000)]
    category: Category = Category.OTHER
    priority: Priority = Priority.MEDIUM
    status: Status = Status.NEW
    assigned_to: Annotated[str, Field(max_length=255)] | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: TicketMetadata = Field(default_factory=TicketMetadata)


class TicketCreate(TicketBase):
    pass


class TicketUpdate(BaseModel):
    customer_id: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    customer_email: EmailStr | None = None
    customer_name: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    subject: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    description: Annotated[str, Field(min_length=10, max_length=2000)] | None = None
    category: Category | None = None
    priority: Priority | None = None
    status: Status | None = None
    assigned_to: Annotated[str, Field(max_length=255)] | None = None
    tags: list[str] | None = None
    metadata: TicketMetadata | None = None
    resolved_at: datetime | None = None


class TicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: str
    customer_email: EmailStr
    customer_name: str
    subject: str
    description: str
    category: Category
    priority: Priority
    status: Status
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    assigned_to: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    classification_confidence: float | None = None


class TicketListResponse(BaseModel):
    items: list[TicketRead]
    total: int
    limit: int
    offset: int


class TicketFilter(BaseModel):
    category: Category | None = None
    priority: Priority | None = None
    status: Status | None = None
    customer_id: str | None = None
    assigned_to: str | None = None
    limit: Annotated[int, Field(ge=1, le=200)] = 50
    offset: Annotated[int, Field(ge=0)] = 0
