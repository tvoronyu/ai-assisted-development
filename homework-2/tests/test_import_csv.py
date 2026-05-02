from pathlib import Path

import pytest
from httpx import AsyncClient

from src.parsers.base import ParserError
from src.parsers.csv_parser import CsvTicketParser

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.integration
def test_csv_parser_parses_50_records_from_sample() -> None:
    content = (FIXTURES / "sample_tickets.csv").read_bytes()
    records = list(CsvTicketParser().parse(content))
    assert len(records) == 50
    assert records[0]["customer_id"]
    assert records[0]["customer_email"]


@pytest.mark.integration
def test_csv_parser_handles_only_header_row() -> None:
    content = b"customer_id,customer_email,customer_name,subject,description\n"
    records = list(CsvTicketParser().parse(content))
    assert records == []


@pytest.mark.integration
def test_csv_parser_raises_on_empty_file() -> None:
    with pytest.raises(ParserError):
        list(CsvTicketParser().parse(b""))


@pytest.mark.integration
async def test_import_csv_endpoint_succeeds_for_valid_sample(client: AsyncClient) -> None:
    content = (FIXTURES / "sample_tickets.csv").read_bytes()
    files = {"file": ("sample_tickets.csv", content, "text/csv")}
    response = await client.post("/tickets/import", files=files)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 50
    assert body["successful"] == 50
    assert body["failed"] == 0
    assert len(body["created_ids"]) == 50


@pytest.mark.integration
async def test_import_csv_endpoint_reports_per_row_errors(client: AsyncClient) -> None:
    content = (FIXTURES / "invalid_tickets.csv").read_bytes()
    files = {"file": ("invalid_tickets.csv", content, "text/csv")}
    response = await client.post("/tickets/import", files=files)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["successful"] == 0
    assert body["failed"] == 3
    assert len(body["errors"]) == 3


@pytest.mark.integration
async def test_import_endpoint_rejects_unsupported_extension(client: AsyncClient) -> None:
    files = {"file": ("data.txt", b"hello", "text/plain")}
    response = await client.post("/tickets/import", files=files)
    assert response.status_code == 400
