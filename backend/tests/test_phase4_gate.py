"""Phase 4 dispatch, form, and final-gate checkpoint coverage."""

import asyncio
import re
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import SessionLocal
from app.mail import Mailer
from app.models import AuditLog, EmailOutbox, Request, Vendor
from app.services.gate import run as run_gate
from app.services.tokens import create

FIXTURES = Path(__file__).parents[1] / "fixtures"


def sample_payload(thread_id: str, message_id: str) -> dict[str, str]:
    """Return the Phase 2 sample in the manual intake boundary format."""

    content = (FIXTURES / "sample_email.txt").read_text()
    content = content.replace("Acme Supplies Ltd", f"Phase Four {thread_id} Supplies")
    _, body = content.split("\n\n", 1)
    return {
        "from": content.splitlines()[0].removeprefix("From: "),
        "subject": content.splitlines()[1].removeprefix("Subject: "),
        "body": body,
        "thread_id": thread_id,
        "message_id": message_id,
    }


async def make_ready_request(suffix: str, **overrides: str | None) -> str:
    """Persist a request whose four gate clearances can be independently varied."""

    tracking_id = f"VR-phase4-{suffix}"
    values: dict[str, str | None] = {
        "financial_clearance": "cleared_automatically",
        "duplicate_clearance": "cleared_automatically",
        "documents_clearance": "accepted",
        "compliance_clearance": "clear",
    }
    values.update(overrides)
    async with SessionLocal.begin() as session:
        session.add(
            Request(
                tracking_id=tracking_id,
                thread_id=f"phase4-{suffix}",
                message_ids=[],
                status="awaiting_actions",
                request_json={},
                vendor_id=f"VEN-phase4-{suffix}",
                requestor_email="requestor@example.test",
                company_name="Phase Four Supplies Ltd",
                vendor_country="Singapore",
                documentation_contact="Docs (docs@example.test)",
                authorized_contact="Owner (owner@example.test)",
                payment_terms_days=100,
                estimated_annual_spend_usd=50_000,
                currency="USD",
                **values,
            )
        )
    return tracking_id


async def outbox_token(tracking_id: str, kind: str) -> str:
    """Extract a raw token only from its intentionally local ConsoleMailer outbox entry."""

    async with SessionLocal() as session:
        message = await session.scalar(
            select(EmailOutbox).where(
                EmailOutbox.tracking_id == tracking_id, EmailOutbox.kind == kind
            )
        )
        assert message is not None
        match = re.search(r"/forms/(?:manager|duplicate)/([A-Za-z0-9_-]+)", message.body)
        assert match is not None
        return match.group(1)


def test_dispatches_independent_manager_and_document_actions(client: TestClient) -> None:
    """Escalation and upload links are emitted together and document time is stamped."""

    suffix = uuid4().hex
    response = client.post("/intake/email", json=sample_payload(suffix, f"message-{suffix}"))
    assert response.json()["outcome"] == "pending_manager"

    async def scenario() -> None:
        tracking_id = f"VR-{suffix}"
        async with SessionLocal() as session:
            request = await session.get(Request, tracking_id)
            assert request is not None
            assert request.status == "awaiting_actions"
            assert request.documents_requested_at is not None
            kinds = set(
                (
                    await session.scalars(
                        select(EmailOutbox.kind).where(EmailOutbox.tracking_id == tracking_id)
                    )
                ).all()
            )
            assert {"manager_decision", "document_request"} <= kinds

    asyncio.run(scenario())


def test_manager_approval_creates_vendor_and_second_gate_skips(client: TestClient) -> None:
    """An approved, document-ready request creates one vendor and sends three notices."""

    suffix = uuid4().hex
    tracking_id = f"VR-{suffix}"
    intake = client.post("/intake/email", json=sample_payload(suffix, f"message-{suffix}"))
    assert intake.json()["outcome"] == "pending_manager"

    async def accept_documents() -> None:
        async with SessionLocal.begin() as session:
            request = await session.get(Request, tracking_id)
            assert request is not None
            request.documents_clearance = "accepted"

    asyncio.run(accept_documents())
    token = asyncio.run(outbox_token(tracking_id, "manager_decision"))
    response = client.post(
        f"/forms/manager/{token}", data={"decision": "approve", "comments": "ok"}
    )
    assert "CREATE" in response.text
    assert client.post(f"/gate/{tracking_id}").json()["outcome"] == "SKIP"

    async def scenario() -> None:
        async with SessionLocal() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(Vendor)
                .where(Vendor.request_tracking_id == tracking_id)
            )
            assert count == 1
            kinds = set(
                (
                    await session.scalars(
                        select(EmailOutbox.kind).where(EmailOutbox.tracking_id == tracking_id)
                    )
                ).all()
            )
            assert {
                "vendor_created_requestor",
                "vendor_created_vendor",
                "vendor_created_master_data",
            } <= kinds

    asyncio.run(scenario())


def test_manager_rejection_holds_without_creating_vendor(client: TestClient) -> None:
    """Rejected sourcing decisions are terminal and do not create a vendor."""

    suffix = uuid4().hex
    tracking_id = f"VR-{suffix}"
    intake = client.post("/intake/email", json=sample_payload(suffix, f"message-{suffix}"))
    assert intake.json()["outcome"] == "pending_manager"
    token = asyncio.run(outbox_token(tracking_id, "manager_decision"))
    response = client.post(f"/forms/manager/{token}", data={"decision": "reject", "comments": "no"})
    assert "HOLD" in response.text

    async def scenario() -> None:
        async with SessionLocal() as session:
            request = await session.get(Request, tracking_id)
            assert request is not None
            assert request.status == "on_hold_financial"
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Vendor)
                    .where(Vendor.request_tracking_id == tracking_id)
                )
                == 0
            )

    asyncio.run(scenario())


def test_duplicate_form_and_hold_beats_wait(client: TestClient) -> None:
    """Human duplicate clearance can create; a rejection wins over pending documents."""

    async def scenario() -> tuple[str, str]:
        review_tracking = await make_ready_request(
            uuid4().hex, duplicate_clearance="pending_review"
        )
        hold_tracking = await make_ready_request(
            uuid4().hex,
            financial_clearance="rejected_by_sourcing_manager",
            documents_clearance="pending_upload",
        )
        async with SessionLocal.begin() as session:
            token = await create(session, review_tracking, "duplicate_review")
            hold_result = await run_gate(session, hold_tracking, client.app.state.mailer)
            assert hold_result.outcome == "HOLD"
        return review_tracking, token

    review_tracking, token = asyncio.run(scenario())
    response = client.post(
        f"/forms/duplicate/{token}", data={"decision": "not_duplicate", "comments": "checked"}
    )
    assert "CREATE" in response.text

    async def verify_created() -> None:
        async with SessionLocal() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Vendor)
                    .where(Vendor.request_tracking_id == review_tracking)
                )
                == 1
            )

    asyncio.run(verify_created())


def test_concurrent_gate_calls_create_one_vendor() -> None:
    """The row lock and database unique constraint close the final-gate race window."""

    async def scenario() -> None:
        tracking_id = await make_ready_request(uuid4().hex)

        async def one_call() -> str:
            from app.main import app

            async with SessionLocal.begin() as session:
                return (await run_gate(session, tracking_id, app.state.mailer)).outcome

        outcomes = await asyncio.gather(*(one_call() for _ in range(20)))
        assert outcomes.count("CREATE") == 1
        async with SessionLocal() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Vendor)
                    .where(Vendor.request_tracking_id == tracking_id)
                )
                == 1
            )

    asyncio.run(scenario())


class FailingMailer(Mailer):
    """Transport used to prove notification failures do not roll back creation."""

    async def deliver(self, recipient: str, subject: str, body: str) -> str:
        raise RuntimeError("intentional delivery failure")


def test_notification_failure_does_not_undo_created_vendor(monkeypatch: pytest.MonkeyPatch) -> None:
    """The vendor transaction commits even if all final notifications fail."""

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("app.mail.asyncio.sleep", no_sleep)

    async def scenario() -> None:
        tracking_id = await make_ready_request(uuid4().hex)
        async with SessionLocal.begin() as session:
            assert (await run_gate(session, tracking_id, FailingMailer())).outcome == "CREATE"
        async with SessionLocal() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Vendor)
                    .where(Vendor.request_tracking_id == tracking_id)
                )
                == 1
            )

    asyncio.run(scenario())


def test_manager_more_information_reply_resumes_without_rescreening(client: TestClient) -> None:
    """A same-thread correction re-runs finance but retains prior compliance screening."""

    suffix = uuid4().hex
    tracking_id = f"VR-{suffix}"
    original = sample_payload(suffix, f"message-{suffix}")
    intake = client.post("/intake/email", json=original)
    assert intake.json()["outcome"] == "pending_manager"
    token = asyncio.run(outbox_token(tracking_id, "manager_decision"))
    response = client.post(
        f"/forms/manager/{token}", data={"decision": "more_info", "comments": "reduce spend"}
    )
    assert "MORE_INFO" in response.text

    corrected = sample_payload(suffix, f"reply-{suffix}")
    corrected["body"] = corrected["body"].replace("$150,000 USD", "$50,000 USD")
    assert client.post("/intake/email", json=corrected).json()["outcome"] == "cleared_automatically"

    async def scenario() -> None:
        async with SessionLocal() as session:
            compliance_events = await session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.tracking_id == tracking_id, AuditLog.stage == "compliance")
            )
            assert compliance_events == 1
            request = await session.get(Request, tracking_id)
            assert request is not None
            assert request.financial_clearance == "cleared_automatically"

    asyncio.run(scenario())
