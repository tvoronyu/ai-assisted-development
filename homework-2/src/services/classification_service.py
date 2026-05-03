import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.ticket import Ticket
from src.schemas.classification import ClassificationResult
from src.services.classifier import TicketClassifier

logger = logging.getLogger(__name__)


class ClassificationService:
    def __init__(
        self,
        session: AsyncSession,
        classifier: TicketClassifier | None = None,
    ) -> None:
        self.session = session
        self.classifier = classifier or TicketClassifier()

    async def classify_ticket(
        self, ticket: Ticket
    ) -> ClassificationResult:
        result = self.classifier.classify(ticket.subject, ticket.description)
        ticket.category = result.category
        ticket.priority = result.priority
        ticket.classification_confidence = result.confidence
        await self.session.commit()
        await self.session.refresh(ticket)

        logger.info(
            "auto_classify ticket=%s category=%s priority=%s confidence=%.2f",
            ticket.id,
            result.category.value,
            result.priority.value,
            result.confidence,
        )
        return result

    async def classify_by_id(
        self, ticket_id: UUID
    ) -> tuple[Ticket, ClassificationResult] | None:
        ticket = await self.session.get(Ticket, ticket_id)
        if ticket is None:
            return None
        result = await self.classify_ticket(ticket)
        return ticket, result
