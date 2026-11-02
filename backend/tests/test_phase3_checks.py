"""Phase 3 compliance, financial, duplicate, and requirements checkpoint tests."""

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db import SessionLocal
from app.models import AuditLog, EmailOutbox, Request
from app.services.duplicates import detect, dice_coefficient
from app.services.financial import evaluate

FIXTURES = Path(__file__).parents[1] / "fixtures"


def email_payload(
    fixture_name: str,
    thread_id: str,
    message_id: str,
    replacements: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build an intake payload and optionally mutate literal fixture values."""

    content = (FIXTURES / fixture_name).read_text()
    for old, new in (replacements or {}).items():
        content = content.replace(old, new)
    _, body = content.split("\n\n", 1)
    return {
        "from": content.splitlines()[0].removeprefix("From: "),
        "subject": content.splitlines()[1].removeprefix("Subject: "),
        "body": body,
        "thread_id": thread_id,
        "message_id": message_id,
    }


async def request_for(tracking_id: str) -> Request:
    """Load the shared workflow state following a committed endpoint request."""

    async with SessionLocal() as session:
        request = await session.get(Request, tracking_id)
        assert request is not None
        return request


def test_financial_rules_cover_exact_boundaries() -> None:
    """R1–R5 preserve their first-match order and USD-only behaviour."""

    assert evaluate(None, 100, "USD").clearance == "pending_financial_data"
    assert evaluate(60, 100, "SGD").clearance == "pending_financial_data"
    assert evaluate(44, 1, "USD").clearance == "pending_manager"
    assert evaluate(45, 100_000, "USD").clearance == "cleared_automatically"
    assert evaluate(89, 100_000, "USD").clearance == "cleared_automatically"
    assert evaluate(89, 100_001, "USD").clearance == "pending_manager"
    assert evaluate(90, 1, "USD").clearance == "cleared_automatically"


def test_sample_escalates_and_resolves_singapore_requirements(client: TestClient) -> None:
    """A valid Singapore request escalates financially and awaits its known documents."""

    suffix = uuid4().hex
    response = client.post(
        "/intake/email",
        json=email_payload("sample_email.txt", suffix, f"message-{suffix}"),
    )

    assert response.json()["outcome"] == "pending_manager"
    request = asyncio.run(request_for(f"VR-{suffix}"))
    assert request.compliance_clearance == "clear"
    assert request.financial_clearance == "pending_manager"
    assert request.duplicate_clearance == "cleared_automatically"
    assert request.documents_clearance == "pending_upload"


@pytest.mark.parametrize(
    ("company_name", "expected_clearance"),
    [
        ("Lab Review Vendor", "flagged_for_review"),
        ("Lab Error Vendor", "verification_error"),
    ],
)
def test_simulated_compliance_holds_without_vendor_or_manager_messages(
    client: TestClient, company_name: str, expected_clearance: str
) -> None:
    """Fixture hits notify only the requestor with a generic SIMULATED message."""

    suffix = uuid4().hex
    response = client.post(
        "/intake/email",
        json=email_payload(
            "sample_email.txt",
            suffix,
            f"message-{suffix}",
            {"Acme Supplies Ltd": company_name},
        ),
    )

    assert response.json()["outcome"] == "compliance_hold"

    async def scenario() -> None:
        async with SessionLocal() as session:
            request = await session.get(Request, f"VR-{suffix}")
            assert request is not None
            assert request.compliance_clearance == expected_clearance
            messages = (
                await session.scalars(
                    select(EmailOutbox).where(EmailOutbox.tracking_id == f"VR-{suffix}")
                )
            ).all()
            assert len(messages) == 1
            assert messages[0].recipient == "john.smith@company.com"
            assert "SIMULATED compliance" in messages[0].body
            audit = await session.scalar(
                select(AuditLog).where(
                    AuditLog.tracking_id == f"VR-{suffix}", AuditLog.stage == "compliance"
                )
            )
            assert audit is not None
            assert "SIMULATED" in (audit.reason or "")

    asyncio.run(scenario())


def test_exact_and_similar_vendor_names_take_distinct_paths(client: TestClient) -> None:
    """Exact blocks; the documented Harbour spelling falls in the review band."""

    exact = uuid4().hex
    response = client.post(
        "/intake/email",
        json=email_payload(
            "sample_email.txt",
            exact,
            f"message-{exact}",
            {"Acme Supplies Ltd": "Harbor Office Supplies"},
        ),
    )
    assert response.json()["outcome"] == "blocked_duplicate"
    assert asyncio.run(request_for(f"VR-{exact}")).duplicate_clearance == "blocked_duplicate"

    similar = uuid4().hex
    response = client.post(
        "/intake/email",
        json=email_payload(
            "sample_email.txt",
            similar,
            f"message-{similar}",
            {"Acme Supplies Ltd": "Harbour Office Supply"},
        ),
    )
    assert response.json()["outcome"] == "pending_manager"
    request = asyncio.run(request_for(f"VR-{similar}"))
    assert request.duplicate_clearance == "pending_review"
    score = dice_coefficient("harbor office supplies", "harbour office supply")
    assert score == pytest.approx(0.811, abs=0.01)


def test_vendor_master_read_error_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A database read failure cannot be misrepresented as no duplicate."""

    async def scenario() -> None:
        class BrokenSession:
            async def scalars(self, statement):
                raise SQLAlchemyError("vendor master unavailable")

        decision = await detect(BrokenSession(), "Any Vendor", "Singapore")
        assert decision.clearance == "blocked_duplicate"

    asyncio.run(scenario())


def test_unknown_country_requires_manual_review_without_checklist(client: TestClient) -> None:
    """Unknown countries route to people instead of receiving an invented checklist."""

    suffix = uuid4().hex
    response = client.post(
        "/intake/email",
        json=email_payload(
            "sample_email.txt",
            suffix,
            f"message-{suffix}",
            {"Singapore": "Atlantis"},
        ),
    )

    assert response.json()["outcome"] == "manual_requirements_review"
    request = asyncio.run(request_for(f"VR-{suffix}"))
    assert request.status == "manual_requirements_review"
    assert request.documents_clearance == "pending_manual_review"
