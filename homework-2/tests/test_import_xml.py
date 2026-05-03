from pathlib import Path

import pytest
from httpx import AsyncClient

from src.parsers.base import ParserError
from src.parsers.xml_parser import XmlTicketParser

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.integration
def test_xml_parser_parses_30_records_from_sample() -> None:
    content = (FIXTURES / "sample_tickets.xml").read_bytes()
    records = list(XmlTicketParser().parse(content))
    assert len(records) == 30


@pytest.mark.integration
def test_xml_parser_extracts_tags_and_metadata() -> None:
    content = (FIXTURES / "sample_tickets.xml").read_bytes()
    records = list(XmlTicketParser().parse(content))
    sample_with_tags = next((r for r in records if r.get("tags")), None)
    assert sample_with_tags is not None
    assert isinstance(sample_with_tags["tags"], list)
    sample_with_metadata = next((r for r in records if r.get("metadata")), None)
    assert sample_with_metadata is not None
    assert "source" in sample_with_metadata["metadata"]


@pytest.mark.integration
def test_xml_parser_raises_on_malformed_xml() -> None:
    content = (FIXTURES / "invalid_tickets.xml").read_bytes()
    with pytest.raises(ParserError):
        list(XmlTicketParser().parse(content))


@pytest.mark.integration
async def test_import_xml_endpoint_succeeds_for_valid_sample(client: AsyncClient) -> None:
    content = (FIXTURES / "sample_tickets.xml").read_bytes()
    files = {"file": ("sample_tickets.xml", content, "application/xml")}
    response = await client.post("/tickets/import", files=files)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 30
    assert body["successful"] == 30
    assert body["failed"] == 0


@pytest.mark.integration
async def test_import_xml_endpoint_reports_parser_error(client: AsyncClient) -> None:
    content = (FIXTURES / "invalid_tickets.xml").read_bytes()
    files = {"file": ("invalid_tickets.xml", content, "application/xml")}
    response = await client.post("/tickets/import", files=files)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["successful"] == 0
    assert body["failed"] == 1
