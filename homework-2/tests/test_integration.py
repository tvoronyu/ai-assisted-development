from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

FIXTURES = Path(__file__).parent / "fixtures"


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
async def test_complete_ticket_lifecycle(client: AsyncClient) -> None:
    create = await client.post(
        "/tickets",
        json=_payload(
            subject="Cannot login",
            description="I am unable to access my account. This is critical, production down.",
        ),
    )
    assert create.status_code == 201
    ticket_id = create.json()["id"]

    classified = await client.post(f"/tickets/{ticket_id}/auto-classify")
    assert classified.status_code == 200
    assert classified.json()["priority"] == "urgent"
    assert classified.json()["category"] == "account_access"

    assigned = await client.put(
        f"/tickets/{ticket_id}",
        json={"assigned_to": "agent-007", "status": "in_progress"},
    )
    assert assigned.status_code == 200
    assert assigned.json()["assigned_to"] == "agent-007"
    assert assigned.json()["status"] == "in_progress"

    resolved = await client.put(
        f"/tickets/{ticket_id}",
        json={"status": "resolved"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["assigned_to"] == "agent-007"
    assert resolved.json()["priority"] == "urgent"

    deleted = await client.delete(f"/tickets/{ticket_id}")
    assert deleted.status_code == 204
    assert (await client.get(f"/tickets/{ticket_id}")).status_code == 404


@pytest.mark.integration
async def test_bulk_import_then_auto_classify_per_ticket(client: AsyncClient) -> None:
    content = (FIXTURES / "sample_tickets.csv").read_bytes()
    files = {"file": ("sample_tickets.csv", content, "text/csv")}
    summary = (await client.post("/tickets/import", files=files)).json()
    assert summary["successful"] == 50

    ids_to_classify = summary["created_ids"][:5]
    for tid in ids_to_classify:
        result = await client.post(f"/tickets/{tid}/auto-classify")
        assert result.status_code == 200
        body = result.json()
        assert body["priority"] in ("urgent", "high", "medium", "low")
        assert body["category"] in (
            "account_access",
            "technical_issue",
            "billing_question",
            "feature_request",
            "bug_report",
            "other",
        )
        assert 0.0 <= body["confidence"] <= 1.0
        assert body["reasoning"]


@pytest.mark.integration
async def test_combined_filtering_with_pagination(client: AsyncClient) -> None:
    for i in range(15):
        await client.post(
            "/tickets",
            json=_payload(
                customer_id=f"c-{i}",
                subject=f"Issue {i}",
                category="bug_report" if i % 2 == 0 else "feature_request",
                priority="high" if i < 5 else "medium",
            ),
        )

    response = await client.get(
        "/tickets",
        params={"category": "bug_report", "priority": "high", "limit": 3, "offset": 0},
    )
    assert response.status_code == 200
    body = response.json()
    matching_total = body["total"]
    assert matching_total >= 1
    assert len(body["items"]) <= 3
    for item in body["items"]:
        assert item["category"] == "bug_report"
        assert item["priority"] == "high"

    page2 = await client.get(
        "/tickets",
        params={"category": "bug_report", "priority": "high", "limit": 3, "offset": 3},
    )
    assert page2.json()["total"] == matching_total


@pytest.mark.integration
async def test_bulk_import_with_mixed_valid_invalid_records(client: AsyncClient) -> None:
    content = (FIXTURES / "invalid_tickets.csv").read_bytes()
    files = {"file": ("invalid_tickets.csv", content, "text/csv")}
    response = await client.post("/tickets/import", files=files)
    assert response.status_code == 200
    summary = response.json()
    assert summary["total"] == 3
    assert summary["successful"] == 0
    assert summary["failed"] == 3
    assert len(summary["errors"]) == 3
    error_rows = sorted(e["row"] for e in summary["errors"])
    assert error_rows == [1, 2, 3]

    listed = await client.get("/tickets")
    assert listed.json()["total"] == 0


@pytest.mark.integration
async def test_partial_update_preserves_unmodified_fields(client: AsyncClient) -> None:
    created = (
        await client.post(
            "/tickets",
            json=_payload(
                subject="Original subject",
                description="A long original description that we should keep intact.",
                category="billing_question",
                priority="high",
                assigned_to="agent-1",
                tags=["billing", "urgent"],
            ),
        )
    ).json()

    response = await client.put(
        f"/tickets/{created['id']}",
        json={"status": "waiting_customer"},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "waiting_customer"
    assert body["subject"] == "Original subject"
    assert body["description"].startswith("A long original")
    assert body["category"] == "billing_question"
    assert body["priority"] == "high"
    assert body["assigned_to"] == "agent-1"
    assert sorted(body["tags"]) == ["billing", "urgent"]
