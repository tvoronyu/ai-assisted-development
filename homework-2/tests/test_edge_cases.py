from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


def _payload(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "customer_id": "cust-1",
        "customer_email": "user@example.com",
        "customer_name": "User",
        "subject": "Generic subject",
        "description": "A long enough description for validation purposes here.",
    }
    base.update(overrides)
    return base


@pytest.mark.integration
async def test_update_ticket_replaces_metadata(client: AsyncClient) -> None:
    created = (await client.post("/tickets", json=_payload())).json()
    response = await client.put(
        f"/tickets/{created['id']}",
        json={"metadata": {"source": "email", "browser": "Chrome 121", "device_type": "mobile"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["source"] == "email"
    assert body["metadata"]["browser"] == "Chrome 121"
    assert body["metadata"]["device_type"] == "mobile"


@pytest.mark.integration
async def test_update_ticket_replaces_tags(client: AsyncClient) -> None:
    created = (await client.post("/tickets", json=_payload())).json()
    response = await client.put(
        f"/tickets/{created['id']}",
        json={"tags": ["urgent", "billing"]},
    )
    assert response.status_code == 200
    assert response.json()["tags"] == ["urgent", "billing"]


@pytest.mark.integration
async def test_update_ticket_with_null_metadata_clears_to_empty(client: AsyncClient) -> None:
    created = (
        await client.post(
            "/tickets",
            json=_payload(metadata={"source": "email", "browser": "X", "device_type": "desktop"}),
        )
    ).json()
    assert created["metadata"]["source"] == "email"

    response = await client.put(f"/tickets/{created['id']}", json={"metadata": None})
    assert response.status_code == 200
    assert response.json()["metadata"] == {}


@pytest.mark.integration
async def test_update_ticket_with_null_tags_clears_to_empty(client: AsyncClient) -> None:
    created = (await client.post("/tickets", json=_payload(tags=["a", "b"]))).json()
    assert created["tags"] == ["a", "b"]

    response = await client.put(f"/tickets/{created['id']}", json={"tags": None})
    assert response.status_code == 200
    assert response.json()["tags"] == []


@pytest.mark.integration
async def test_list_tickets_filters_by_customer_id(client: AsyncClient) -> None:
    await client.post("/tickets", json=_payload(customer_id="alice"))
    await client.post("/tickets", json=_payload(customer_id="bob"))
    await client.post("/tickets", json=_payload(customer_id="alice"))

    response = await client.get("/tickets", params={"customer_id": "alice"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert all(t["customer_id"] == "alice" for t in body["items"])


@pytest.mark.integration
async def test_list_tickets_filters_by_assigned_to(client: AsyncClient) -> None:
    await client.post("/tickets", json=_payload(assigned_to="agent-1"))
    await client.post("/tickets", json=_payload(assigned_to="agent-2"))
    await client.post("/tickets", json=_payload())  # unassigned

    response = await client.get("/tickets", params={"assigned_to": "agent-1"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["assigned_to"] == "agent-1"


@pytest.mark.integration
async def test_delete_ticket_returns_404_when_missing(client: AsyncClient) -> None:
    response = await client.delete("/tickets/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.integration
async def test_auto_classify_returns_404_when_missing(client: AsyncClient) -> None:
    response = await client.post(
        "/tickets/00000000-0000-0000-0000-000000000000/auto-classify"
    )
    assert response.status_code == 404


@pytest.mark.integration
async def test_get_session_yields_async_session() -> None:
    from src.db.session import get_session

    session = None
    async for s in get_session():
        session = s
        break
    assert session is not None
    assert isinstance(session, AsyncSession)


@pytest.mark.unit
def test_configure_logging_does_not_raise() -> None:
    from src.logging_config import configure_logging

    configure_logging()
