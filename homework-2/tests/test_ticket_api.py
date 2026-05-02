from typing import Any

import pytest
from httpx import AsyncClient


def _valid_payload(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "customer_id": "cust-1",
        "customer_email": "alice@example.com",
        "customer_name": "Alice",
        "subject": "Cannot access account",
        "description": "I am unable to log in to my account from any browser.",
    }
    base.update(overrides)
    return base


@pytest.mark.integration
async def test_create_ticket_returns_201_and_full_payload(client: AsyncClient) -> None:
    response = await client.post("/tickets", json=_valid_payload())
    assert response.status_code == 201
    data = response.json()
    assert data["customer_id"] == "cust-1"
    assert data["customer_email"] == "alice@example.com"
    assert data["status"] == "new"
    assert data["priority"] == "medium"
    assert data["category"] == "other"
    assert data["tags"] == []
    assert data["metadata"] == {}
    assert "id" in data
    assert "created_at" in data


@pytest.mark.integration
async def test_create_ticket_with_invalid_email_returns_422(client: AsyncClient) -> None:
    response = await client.post(
        "/tickets",
        json=_valid_payload(customer_email="not-an-email"),
    )
    assert response.status_code == 422


@pytest.mark.integration
async def test_create_ticket_with_short_description_returns_422(client: AsyncClient) -> None:
    response = await client.post(
        "/tickets",
        json=_valid_payload(description="too short"),
    )
    assert response.status_code == 422


@pytest.mark.integration
async def test_get_ticket_returns_200_when_exists(client: AsyncClient) -> None:
    created = (await client.post("/tickets", json=_valid_payload())).json()
    response = await client.get(f"/tickets/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


@pytest.mark.integration
async def test_get_ticket_returns_404_when_missing(client: AsyncClient) -> None:
    response = await client.get("/tickets/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.integration
async def test_list_tickets_returns_pagination_meta(client: AsyncClient) -> None:
    for i in range(3):
        await client.post("/tickets", json=_valid_payload(customer_id=f"c-{i}"))
    response = await client.get("/tickets")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert len(body["items"]) == 3


@pytest.mark.integration
async def test_list_tickets_filters_by_category(client: AsyncClient) -> None:
    await client.post("/tickets", json=_valid_payload(category="billing_question"))
    await client.post("/tickets", json=_valid_payload(category="bug_report"))
    await client.post("/tickets", json=_valid_payload(category="bug_report"))

    response = await client.get("/tickets", params={"category": "bug_report"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert all(t["category"] == "bug_report" for t in body["items"])


@pytest.mark.integration
async def test_list_tickets_filters_by_priority_and_status(client: AsyncClient) -> None:
    await client.post("/tickets", json=_valid_payload(priority="urgent", status="new"))
    await client.post("/tickets", json=_valid_payload(priority="urgent", status="resolved"))
    await client.post("/tickets", json=_valid_payload(priority="low", status="new"))

    response = await client.get(
        "/tickets",
        params={"priority": "urgent", "status": "new"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["priority"] == "urgent"
    assert body["items"][0]["status"] == "new"


@pytest.mark.integration
async def test_update_ticket_returns_200_and_modified_fields(client: AsyncClient) -> None:
    created = (await client.post("/tickets", json=_valid_payload())).json()
    response = await client.put(
        f"/tickets/{created['id']}",
        json={"status": "in_progress", "assigned_to": "agent-007"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "in_progress"
    assert body["assigned_to"] == "agent-007"
    assert body["customer_email"] == "alice@example.com"


@pytest.mark.integration
async def test_update_ticket_returns_404_when_missing(client: AsyncClient) -> None:
    response = await client.put(
        "/tickets/00000000-0000-0000-0000-000000000000",
        json={"status": "resolved"},
    )
    assert response.status_code == 404


@pytest.mark.integration
async def test_delete_ticket_returns_204_then_404(client: AsyncClient) -> None:
    created = (await client.post("/tickets", json=_valid_payload())).json()
    delete_response = await client.delete(f"/tickets/{created['id']}")
    assert delete_response.status_code == 204
    follow_up = await client.get(f"/tickets/{created['id']}")
    assert follow_up.status_code == 404


@pytest.mark.integration
async def test_list_tickets_pagination_with_limit_and_offset(client: AsyncClient) -> None:
    for i in range(5):
        await client.post("/tickets", json=_valid_payload(customer_id=f"c-{i}"))

    page1 = (await client.get("/tickets", params={"limit": 2, "offset": 0})).json()
    page2 = (await client.get("/tickets", params={"limit": 2, "offset": 2})).json()
    page3 = (await client.get("/tickets", params={"limit": 2, "offset": 4})).json()

    assert page1["total"] == 5
    assert page2["total"] == 5
    assert page3["total"] == 5
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 2
    assert len(page3["items"]) == 1
    ids = {t["id"] for t in page1["items"] + page2["items"] + page3["items"]}
    assert len(ids) == 5
