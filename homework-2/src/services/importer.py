from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.ticket import Ticket
from src.parsers.base import ParserError, TicketParser
from src.parsers.csv_parser import CsvTicketParser
from src.parsers.json_parser import JsonTicketParser
from src.parsers.xml_parser import XmlTicketParser
from src.schemas.import_ import ImportItemError, ImportSummary
from src.schemas.ticket import TicketCreate


def get_parser_for_filename(filename: str) -> TicketParser:
    lower = filename.lower()
    if lower.endswith(".csv"):
        return CsvTicketParser()
    if lower.endswith(".json"):
        return JsonTicketParser()
    if lower.endswith(".xml"):
        return XmlTicketParser()
    raise ValueError(f"Unsupported file extension for {filename!r}")


def _format_validation_error(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "<root>"
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts)


class TicketImporter:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def import_records(
        self, parser: TicketParser, content: bytes
    ) -> ImportSummary:
        try:
            raw_records = list(parser.parse(content))
        except ParserError as exc:
            return ImportSummary(
                total=0,
                successful=0,
                failed=1,
                errors=[ImportItemError(row=0, error=str(exc))],
                created_ids=[],
            )

        total = len(raw_records)
        errors: list[ImportItemError] = []
        created_ids = []

        for idx, raw in enumerate(raw_records, start=1):
            try:
                payload = TicketCreate.model_validate(raw)
            except ValidationError as exc:
                errors.append(
                    ImportItemError(row=idx, error=_format_validation_error(exc))
                )
                continue

            ticket = Ticket(
                customer_id=payload.customer_id,
                customer_email=payload.customer_email,
                customer_name=payload.customer_name,
                subject=payload.subject,
                description=payload.description,
                category=payload.category,
                priority=payload.priority,
                status=payload.status,
                assigned_to=payload.assigned_to,
                tags=list(payload.tags),
                metadata_=payload.metadata.model_dump(exclude_none=True),
            )
            self.session.add(ticket)
            try:
                await self.session.commit()
                await self.session.refresh(ticket)
            except SQLAlchemyError as exc:
                await self.session.rollback()
                errors.append(ImportItemError(row=idx, error=str(exc)))
                continue

            created_ids.append(ticket.id)

        return ImportSummary(
            total=total,
            successful=len(created_ids),
            failed=len(errors),
            errors=errors,
            created_ids=created_ids,
        )
