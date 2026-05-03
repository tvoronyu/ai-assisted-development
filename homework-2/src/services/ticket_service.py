from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.ticket import Ticket
from src.schemas.ticket import TicketCreate, TicketFilter, TicketUpdate


class TicketService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: TicketCreate) -> Ticket:
        ticket = Ticket(
            customer_id=data.customer_id,
            customer_email=data.customer_email,
            customer_name=data.customer_name,
            subject=data.subject,
            description=data.description,
            category=data.category,
            priority=data.priority,
            status=data.status,
            assigned_to=data.assigned_to,
            tags=list(data.tags),
            metadata_=data.metadata.model_dump(exclude_none=True),
        )
        self.session.add(ticket)
        await self.session.commit()
        await self.session.refresh(ticket)
        return ticket

    async def get(self, ticket_id: UUID) -> Ticket | None:
        result = await self.session.execute(
            select(Ticket).where(Ticket.id == ticket_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self, filters: TicketFilter
    ) -> tuple[Sequence[Ticket], int]:
        stmt = select(Ticket)
        count_stmt = select(func.count()).select_from(Ticket)

        if filters.category is not None:
            stmt = stmt.where(Ticket.category == filters.category)
            count_stmt = count_stmt.where(Ticket.category == filters.category)
        if filters.priority is not None:
            stmt = stmt.where(Ticket.priority == filters.priority)
            count_stmt = count_stmt.where(Ticket.priority == filters.priority)
        if filters.status is not None:
            stmt = stmt.where(Ticket.status == filters.status)
            count_stmt = count_stmt.where(Ticket.status == filters.status)
        if filters.customer_id is not None:
            stmt = stmt.where(Ticket.customer_id == filters.customer_id)
            count_stmt = count_stmt.where(Ticket.customer_id == filters.customer_id)
        if filters.assigned_to is not None:
            stmt = stmt.where(Ticket.assigned_to == filters.assigned_to)
            count_stmt = count_stmt.where(Ticket.assigned_to == filters.assigned_to)

        stmt = (
            stmt.order_by(Ticket.created_at.desc())
            .limit(filters.limit)
            .offset(filters.offset)
        )

        total = (await self.session.execute(count_stmt)).scalar_one()
        items = (await self.session.execute(stmt)).scalars().all()
        return items, total

    async def update(
        self, ticket_id: UUID, data: TicketUpdate
    ) -> Ticket | None:
        ticket = await self.get(ticket_id)
        if ticket is None:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key == "metadata":
                ticket.metadata_ = value if value is not None else {}
            elif key == "tags":
                ticket.tags = value if value is not None else []
            else:
                setattr(ticket, key, value)

        await self.session.commit()
        await self.session.refresh(ticket)
        return ticket

    async def delete(self, ticket_id: UUID) -> bool:
        ticket = await self.get(ticket_id)
        if ticket is None:
            return False
        await self.session.delete(ticket)
        await self.session.commit()
        return True
