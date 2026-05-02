from datetime import datetime
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.enums import Category, Priority, Status
from src.models.ticket import Ticket


def _valid_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "customer_id": "cust-1",
        "customer_email": "alice@example.com",
        "customer_name": "Alice",
        "subject": "Cannot login",
        "description": "I am unable to log in to my account from any browser.",
    }
    base.update(overrides)
    return base


@pytest.mark.integration
async def test_create_ticket_with_minimum_fields_uses_defaults(db_session: AsyncSession) -> None:
    ticket = Ticket(**_valid_kwargs())
    db_session.add(ticket)
    await db_session.commit()
    await db_session.refresh(ticket)

    assert isinstance(ticket.id, UUID)
    assert ticket.status == Status.NEW
    assert ticket.priority == Priority.MEDIUM
    assert ticket.category == Category.OTHER
    assert ticket.tags == []
    assert ticket.metadata_ == {}
    assert ticket.classification_confidence is None
    assert ticket.assigned_to is None
    assert ticket.resolved_at is None


@pytest.mark.integration
async def test_create_ticket_sets_server_timestamps(db_session: AsyncSession) -> None:
    ticket = Ticket(**_valid_kwargs())
    db_session.add(ticket)
    await db_session.commit()
    await db_session.refresh(ticket)

    assert isinstance(ticket.created_at, datetime)
    assert isinstance(ticket.updated_at, datetime)
    assert ticket.created_at.tzinfo is not None
    assert ticket.updated_at.tzinfo is not None


@pytest.mark.integration
async def test_subject_is_required(db_session: AsyncSession) -> None:
    kwargs = _valid_kwargs()
    kwargs.pop("subject")
    ticket = Ticket(**kwargs)
    db_session.add(ticket)
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.integration
async def test_description_is_required(db_session: AsyncSession) -> None:
    kwargs = _valid_kwargs()
    kwargs.pop("description")
    ticket = Ticket(**kwargs)
    db_session.add(ticket)
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.integration
async def test_customer_email_is_required(db_session: AsyncSession) -> None:
    kwargs = _valid_kwargs()
    kwargs.pop("customer_email")
    ticket = Ticket(**kwargs)
    db_session.add(ticket)
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.integration
async def test_subject_max_length_200(db_session: AsyncSession) -> None:
    ticket = Ticket(**_valid_kwargs(subject="x" * 201))
    db_session.add(ticket)
    with pytest.raises(DBAPIError):
        await db_session.commit()


@pytest.mark.integration
async def test_description_max_length_2000(db_session: AsyncSession) -> None:
    ticket = Ticket(**_valid_kwargs(description="x" * 2001))
    db_session.add(ticket)
    with pytest.raises(DBAPIError):
        await db_session.commit()


@pytest.mark.integration
async def test_invalid_priority_value_rejected_by_enum(db_session: AsyncSession) -> None:
    with pytest.raises(DBAPIError):
        await db_session.execute(
            text(
                "INSERT INTO tickets "
                "(customer_id, customer_email, customer_name, subject, description, priority) "
                "VALUES ('c1', 'a@example.com', 'Alice', 's', "
                "'long enough description here', 'P0')"
            )
        )
        await db_session.commit()


@pytest.mark.integration
async def test_invalid_category_value_rejected_by_enum(db_session: AsyncSession) -> None:
    with pytest.raises(DBAPIError):
        await db_session.execute(
            text(
                "INSERT INTO tickets "
                "(customer_id, customer_email, customer_name, subject, description, category) "
                "VALUES ('c1', 'a@example.com', 'Alice', 's', "
                "'long enough description here', 'invalid_category')"
            )
        )
        await db_session.commit()
