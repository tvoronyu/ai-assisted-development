from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.deps import SessionDep
from src.schemas.classification import ClassificationResult
from src.services.classification_service import ClassificationService

router = APIRouter(prefix="/tickets", tags=["tickets-classify"])


def get_classification_service(session: SessionDep) -> ClassificationService:
    return ClassificationService(session)


ClassificationServiceDep = Annotated[ClassificationService, Depends(get_classification_service)]


@router.post(
    "/{ticket_id}/auto-classify",
    response_model=ClassificationResult,
)
async def auto_classify_ticket(
    ticket_id: UUID,
    service: ClassificationServiceDep,
) -> ClassificationResult:
    outcome = await service.classify_by_id(ticket_id)
    if outcome is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    _ticket, result = outcome
    return result
