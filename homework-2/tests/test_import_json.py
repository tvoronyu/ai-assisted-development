import json
from pathlib import Path

import pytest
from httpx import AsyncClient

from src.parsers.base import ParserError
from src.parsers.json_parser import JsonTicketParser

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.integration
def test_json_parser_parses_20_records_from_sample() -> None:
    content = (FIXTURES / "sample_tickets.json").read_bytes()
    records = list(JsonTicketParser().parse(content))
    assert len(records) == 20


@pytest.mark.integration
def test_json_parser_accepts_wrapped_object_with_tickets_key() -> None:
    payload = json.dumps({"tickets": [{"customer_id": "c1"}, {"customer_id": "c2"}]}).encode()
    records = list(JsonTicketParser().parse(payload))
    assert len(records) == 2
    assert records[0]["customer_id"] == "c1"


@pytest.mark.integration
def test_json_parser_raises_on_malformed_json() -> None:
    content = (FIXTURES / "invalid_tickets.json").read_bytes()
    with pytest.raises(ParserError):
        list(JsonTicketParser().parse(content))


@pytest.mark.integration
async def test_import_json_endpoint_succeeds_for_valid_sample(client: AsyncClient) -> None:
    content = (FIXTURES / "sample_tickets.json").read_bytes()
    files = {"file": ("sample_tickets.json", content, "application/json")}
    response = await client.post("/tickets/import", files=files)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 20
    assert body["successful"] == 20
    assert body["failed"] == 0


@pytest.mark.integration
async def test_import_json_endpoint_reports_parser_error(client: AsyncClient) -> None:
    content = (FIXTURES / "invalid_tickets.json").read_bytes()
    files = {"file": ("invalid_tickets.json", content, "application/json")}
    response = await client.post("/tickets/import", files=files)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["successful"] == 0
    assert body["failed"] == 1
    assert len(body["errors"]) == 1
