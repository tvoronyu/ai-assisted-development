from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ARRAY, DateTime, Float, String, func, text
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base
from src.models.enums import Category, Priority, Status


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    customer_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    customer_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)

    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False)

    category: Mapped[Category] = mapped_column(
        PgEnum(
            Category,
            name="ticket_category",
            create_type=True,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=Category.OTHER,
        index=True,
    )
    priority: Mapped[Priority] = mapped_column(
        PgEnum(
            Priority,
            name="ticket_priority",
            create_type=True,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=Priority.MEDIUM,
        index=True,
    )
    status: Mapped[Status] = mapped_column(
        PgEnum(
            Status,
            name="ticket_status",
            create_type=True,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=Status.NEW,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    assigned_to: Mapped[str | None] = mapped_column(String(255), nullable=True)

    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        default=list,
        server_default="{}",
    )

    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
