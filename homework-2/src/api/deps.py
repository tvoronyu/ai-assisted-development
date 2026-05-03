from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_session
from src.services.ticket_service import TicketService

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_ticket_service(session: SessionDep) -> TicketService:
    return TicketService(session)


TicketServiceDep = Annotated[TicketService, Depends(get_ticket_service)]
