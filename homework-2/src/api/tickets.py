from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from src.api.classify import ClassificationServiceDep
from src.api.deps import TicketServiceDep
from src.models.enums import Category, Priority, Status
from src.schemas.ticket import (
    TicketCreate,
    TicketFilter,
    TicketListResponse,
    TicketRead,
    TicketUpdate,
)

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TicketRead)
async def create_ticket(
    data: TicketCreate,
    service: TicketServiceDep,
    classifier: ClassificationServiceDep,
    auto_classify: Annotated[bool, Query()] = False,
) -> TicketRead:
    ticket = await service.create(data)
    if auto_classify:
        await classifier.classify_ticket(ticket)
    return TicketRead.model_validate(ticket)


@router.get("", response_model=TicketListResponse)
async def list_tickets(
    service: TicketServiceDep,
    category: Category | None = None,
    priority: Priority | None = None,
    status_filter: Annotated[Status | None, Query(alias="status")] = None,
    customer_id: str | None = None,
    assigned_to: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TicketListResponse:
    filters = TicketFilter(
        category=category,
        priority=priority,
        status=status_filter,
        customer_id=customer_id,
        assigned_to=assigned_to,
        limit=limit,
        offset=offset,
    )
    items, total = await service.list(filters)
    return TicketListResponse(
        items=[TicketRead.model_validate(t) for t in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{ticket_id}", response_model=TicketRead)
async def get_ticket(
    ticket_id: UUID,
    service: TicketServiceDep,
) -> TicketRead:
    ticket = await service.get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return TicketRead.model_validate(ticket)


@router.put("/{ticket_id}", response_model=TicketRead)
async def update_ticket(
    ticket_id: UUID,
    data: TicketUpdate,
    service: TicketServiceDep,
) -> TicketRead:
    ticket = await service.update(ticket_id, data)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return TicketRead.model_validate(ticket)


@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ticket(
    ticket_id: UUID,
    service: TicketServiceDep,
) -> None:
    deleted = await service.delete(ticket_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Ticket not found")
