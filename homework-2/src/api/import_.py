from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from src.api.deps import SessionDep
from src.config import get_settings
from src.schemas.import_ import ImportSummary
from src.services.importer import TicketImporter, get_parser_for_filename

router = APIRouter(prefix="/tickets", tags=["tickets-import"])


@router.post("/import", response_model=ImportSummary)
async def import_tickets(
    session: SessionDep,
    request: Request,
    file: Annotated[UploadFile, File(...)],
) -> ImportSummary:
    settings = get_settings()

    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.max_upload_size_bytes} bytes limit",
        )

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required to detect format",
        )

    try:
        parser = get_parser_for_filename(file.filename)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    content = await file.read()
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.max_upload_size_bytes} bytes limit",
        )

    importer = TicketImporter(session)
    return await importer.import_records(parser, content)
