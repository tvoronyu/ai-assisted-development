from typing import Any

import pytest
from httpx import AsyncClient

from src.models.enums import Category, Priority
from src.schemas.classification import ClassificationResult
from src.services.classifier import (
    CategoryClassifier,
    PriorityClassifier,
    TicketClassifier,
)


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


@pytest.mark.unit
def test_priority_urgent_for_production_down_keyword() -> None:
    score = PriorityClassifier().classify("Production down right now, please help")
    assert score.priority == Priority.URGENT
    assert "production down" in score.keywords


@pytest.mark.unit
def test_priority_high_for_blocking_keyword() -> None:
    score = PriorityClassifier().classify("This is blocking my team's release ASAP")
    assert score.priority == Priority.HIGH


@pytest.mark.unit
def test_priority_low_for_minor_keyword() -> None:
    score = PriorityClassifier().classify("Just a minor cosmetic suggestion")
    assert score.priority == Priority.LOW


@pytest.mark.unit
def test_priority_medium_when_no_keyword_matches() -> None:
    score = PriorityClassifier().classify("Hello, please help with my account")
    assert score.priority == Priority.MEDIUM
    assert score.confidence == 0.5
    assert score.keywords == []


@pytest.mark.unit
def test_category_account_access_for_login_keyword() -> None:
    score = CategoryClassifier().classify("Cannot log in to my account")
    assert score.category == Category.ACCOUNT_ACCESS


@pytest.mark.unit
def test_category_billing_question_for_refund_keyword() -> None:
    score = CategoryClassifier().classify("Please process a refund for invoice 12345")
    assert score.category == Category.BILLING_QUESTION


@pytest.mark.unit
def test_category_other_when_no_keyword_matches() -> None:
    score = CategoryClassifier().classify("Just curious how the platform works")
    assert score.category == Category.OTHER
    assert score.confidence == 0.5


@pytest.mark.unit
def test_classifier_returns_result_with_confidence_reasoning_keywords() -> None:
    result = TicketClassifier().classify(
        subject="Cannot access my account",
        description="The login page returns invalid credentials. This is critical.",
    )
    assert isinstance(result, ClassificationResult)
    assert result.priority == Priority.URGENT
    assert result.category == Category.ACCOUNT_ACCESS
    assert 0.0 <= result.confidence <= 1.0
    assert result.reasoning
    assert len(result.keywords_found) > 0


@pytest.mark.integration
async def test_auto_classify_endpoint_updates_ticket_and_returns_result(
    client: AsyncClient,
) -> None:
    created = (
        await client.post(
            "/tickets",
            json=_payload(
                subject="Cannot login",
                description="I am unable to log in. Critical issue, production down.",
            ),
        )
    ).json()

    response = await client.post(f"/tickets/{created['id']}/auto-classify")
    assert response.status_code == 200
    body = response.json()
    assert body["priority"] == "urgent"
    assert body["category"] == "account_access"
    assert "confidence" in body
    assert "reasoning" in body
    assert "keywords_found" in body

    refreshed = (await client.get(f"/tickets/{created['id']}")).json()
    assert refreshed["priority"] == "urgent"
    assert refreshed["category"] == "account_access"
    assert refreshed["classification_confidence"] is not None


@pytest.mark.integration
async def test_auto_classify_flag_on_create_runs_classifier(client: AsyncClient) -> None:
    response = await client.post(
        "/tickets?auto_classify=true",
        json=_payload(
            subject="Refund request",
            description=(
                "I would like to request a refund for invoice 12345 on my "
                "subscription. The charge was duplicated."
            ),
        ),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["category"] == "billing_question"
    assert body["classification_confidence"] is not None
