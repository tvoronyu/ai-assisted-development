import asyncio
import time
from typing import Any

import pytest
from httpx import AsyncClient

from src.services.classifier import TicketClassifier


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


@pytest.mark.performance
async def test_twenty_concurrent_create_requests_all_succeed(client: AsyncClient) -> None:
    coros = [
        client.post("/tickets", json=_payload(customer_id=f"c-{i}"))
        for i in range(25)
    ]
    start = time.perf_counter()
    responses = await asyncio.gather(*coros)
    elapsed = time.perf_counter() - start

    assert all(r.status_code == 201 for r in responses), [
        (r.status_code, r.text[:120]) for r in responses if r.status_code != 201
    ]
    assert len({r.json()["id"] for r in responses}) == 25
    assert elapsed < 10.0


@pytest.mark.performance
async def test_bulk_import_50_records_under_5_seconds(client: AsyncClient) -> None:
    rows = ["customer_id,customer_email,customer_name,subject,description"]
    for i in range(50):
        rows.append(
            f"c-{i},user{i}@example.com,User {i},Subject {i},"
            f"A long enough description number {i} for validation purposes."
        )
    csv_content = "\n".join(rows).encode()

    start = time.perf_counter()
    response = await client.post(
        "/tickets/import",
        files={"file": ("perf.csv", csv_content, "text/csv")},
    )
    elapsed = time.perf_counter() - start

    assert response.status_code == 200
    assert response.json()["successful"] == 50
    assert elapsed < 5.0


@pytest.mark.performance
async def test_list_1000_tickets_under_2_seconds(client: AsyncClient) -> None:
    rows = ["customer_id,customer_email,customer_name,subject,description"]
    for i in range(1000):
        rows.append(
            f"c-{i:04d},user{i}@example.com,User {i},Subject {i},"
            f"A long enough description #{i} for validation here."
        )
    csv_content = "\n".join(rows).encode()
    summary = (
        await client.post(
            "/tickets/import",
            files={"file": ("bulk.csv", csv_content, "text/csv")},
        )
    ).json()
    assert summary["successful"] == 1000

    start = time.perf_counter()
    response = await client.get("/tickets", params={"limit": 200, "offset": 0})
    elapsed = time.perf_counter() - start

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1000
    assert len(body["items"]) == 200
    assert elapsed < 2.0


@pytest.mark.performance
def test_classifier_processes_100_tickets_under_1_second() -> None:
    classifier = TicketClassifier()
    samples = [
        ("Cannot login", "Critical issue, production down. Cannot access my account."),
        ("Refund please", "Please process refund for invoice 12345 on my subscription."),
        ("App crashes", "The application crashes on startup with stack trace error."),
        ("Feature request", "Would like to suggest adding dark mode feature."),
        ("Bug found", "Steps to reproduce: open dashboard. Expected results, actual empty."),
    ]

    start = time.perf_counter()
    results = []
    for i in range(100):
        subject, description = samples[i % len(samples)]
        results.append(classifier.classify(subject, description))
    elapsed = time.perf_counter() - start

    assert len(results) == 100
    assert all(r.confidence is not None for r in results)
    assert elapsed < 1.0


@pytest.mark.performance
async def test_get_endpoint_p95_latency_under_200ms(client: AsyncClient) -> None:
    created = (await client.post("/tickets", json=_payload())).json()
    ticket_id = created["id"]

    durations = []
    for _ in range(50):
        start = time.perf_counter()
        response = await client.get(f"/tickets/{ticket_id}")
        durations.append(time.perf_counter() - start)
        assert response.status_code == 200

    durations.sort()
    p95_index = int(len(durations) * 0.95)
    p95 = durations[p95_index]
    assert p95 < 0.2, f"p95 latency {p95 * 1000:.1f}ms exceeds 200ms"
