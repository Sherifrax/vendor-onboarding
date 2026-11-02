"""Phase 6 reminder, scheduler-job, and fail-soft error checkpoint coverage."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import SessionLocal
from app.errors import record_error
from app.mail import Mailer
from app.models import AuditLog, EmailOutbox, Request
from app.services.jobs import run_reminders_job
from app.services.reminders import ReminderResult, run


async def create_reminder_request(
    now: datetime,
    age_days: int,
    *,
    clearance: str = "pending_upload",
    reminder_count: int = 0,
) -> str:
    """Create an isolated request with deterministic document-upload age."""

    suffix = uuid4().hex
    tracking_id = f"VR-reminder-{suffix}"
    async with SessionLocal.begin() as session:
        session.add(
            Request(
                tracking_id=tracking_id,
                thread_id=f"reminder-{suffix}",
                message_ids=[],
                status="awaiting_actions",
                request_json={},
                requestor_email="requestor@example.test",
                documentation_contact="Docs (docs@example.test)",
                documents_clearance=clearance,
                documents_requested_at=now - timedelta(days=age_days),
                reminder_count=reminder_count,
            )
        )
    return tracking_id


async def request_by_id(tracking_id: str) -> Request:
    async with SessionLocal() as session:
        request = await session.get(Request, tracking_id)
        assert request is not None
        return request


def test_reminder_ages_and_reruns_are_idempotent() -> None:
    """Day 3/7/10 transitions occur once and day 2 remains silent."""

    now = datetime(2026, 11, 2, 9, tzinfo=UTC)

    async def scenario() -> None:
        from app.mail import ConsoleMailer

        day_two = await create_reminder_request(now, 2)
        day_three = await create_reminder_request(now, 3)
        day_seven = await create_reminder_request(now, 7, reminder_count=1)
        day_ten = await create_reminder_request(now, 10)
        async with SessionLocal.begin() as session:
            result = await run(session, ConsoleMailer(), now=now)
        assert result.first_reminders == 1
        assert result.second_reminders == 1
        assert result.escalations == 1
        assert (await request_by_id(day_two)).reminder_count == 0
        assert (await request_by_id(day_three)).reminder_count == 1
        assert (await request_by_id(day_seven)).reminder_count == 2
        assert (await request_by_id(day_ten)).escalated_at == now

        async with SessionLocal.begin() as session:
            rerun = await run(session, ConsoleMailer(), now=now)
        assert rerun.first_reminders == rerun.second_reminders == rerun.escalations == 0

    asyncio.run(scenario())


def test_pending_review_never_receives_upload_reminder() -> None:
    """Regression for the prior bug that reminded vendors after they had uploaded."""

    now = datetime(2026, 11, 2, 9, tzinfo=UTC)

    async def scenario() -> None:
        from app.mail import ConsoleMailer

        tracking_id = await create_reminder_request(now, 10, clearance="pending_review")
        async with SessionLocal.begin() as session:
            assert await run(session, ConsoleMailer(), now=now) == ReminderResult()
        async with SessionLocal() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(EmailOutbox)
                .where(EmailOutbox.tracking_id == tracking_id)
            )
            assert count == 0

    asyncio.run(scenario())


def test_reminder_endpoint_requires_admin_token(client: TestClient) -> None:
    """The externally-triggered scheduler endpoint is not publicly callable."""

    assert client.post("/jobs/reminders").status_code == 401
    assert client.post("/jobs/reminders", headers={"X-Admin-Token": "change-me"}).status_code == 200


class FailingMailer(Mailer):
    """A mail transport failure that should never prevent the error audit event."""

    async def deliver(self, recipient: str, subject: str, body: str) -> str:
        raise RuntimeError("mail unavailable")


def test_unhandled_pipeline_failure_alerts_and_audits(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pipeline exception gets a generic 500 plus durable alert and ERROR audit record."""

    tracking_id = f"VR-error-{uuid4().hex}"

    async def setup_request() -> None:
        async with SessionLocal.begin() as session:
            session.add(
                Request(
                    tracking_id=tracking_id,
                    thread_id=tracking_id.removeprefix("VR-"),
                    message_ids=[],
                    status="received",
                    request_json={},
                )
            )

    async def broken(*args, **kwargs):
        raise RuntimeError("forced intake failure")

    asyncio.run(setup_request())
    monkeypatch.setattr("app.main.process_email", broken)
    failing_client = TestClient(client.app, raise_server_exceptions=False)
    response = failing_client.post(
        "/intake/email",
        json={
            "from": "requestor@example.test",
            "subject": "failure test",
            "body": "body",
            "thread_id": tracking_id.removeprefix("VR-"),
            "message_id": uuid4().hex,
        },
    )
    assert response.status_code == 500

    async def scenario() -> None:
        async with SessionLocal() as session:
            alert = await session.scalar(
                select(EmailOutbox).where(
                    EmailOutbox.tracking_id == tracking_id,
                    EmailOutbox.kind == "workflow_error_alert",
                )
            )
            audit = await session.scalar(
                select(AuditLog).where(
                    AuditLog.tracking_id == tracking_id, AuditLog.stage == "workflow_error"
                )
            )
            assert alert is not None
            assert audit is not None
            assert audit.status == "ERROR"

    asyncio.run(scenario())


def test_error_audit_survives_email_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """The independent audit transaction is preserved even if alert delivery fails."""

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("app.mail.asyncio.sleep", no_sleep)
    tracking_id = f"VR-error-mail-{uuid4().hex}"

    async def scenario() -> None:
        async with SessionLocal.begin() as session:
            session.add(
                Request(
                    tracking_id=tracking_id,
                    thread_id=tracking_id.removeprefix("VR-"),
                    message_ids=[],
                    status="received",
                    request_json={},
                )
            )
        await record_error(tracking_id, RuntimeError("forced error"), FailingMailer())
        async with SessionLocal() as session:
            audit = await session.scalar(
                select(AuditLog).where(
                    AuditLog.tracking_id == tracking_id, AuditLog.stage == "workflow_error"
                )
            )
            assert audit is not None

    asyncio.run(scenario())


def test_job_wrapper_records_unexpected_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scheduler failures use the same alert and audit path instead of propagating."""

    async def no_sleep(_: float) -> None:
        return None

    async def broken(*args, **kwargs):
        raise RuntimeError("forced reminder job failure")

    monkeypatch.setattr("app.mail.asyncio.sleep", no_sleep)
    monkeypatch.setattr("app.services.jobs.run_reminders", broken)

    async def scenario() -> None:
        from app.mail import ConsoleMailer

        assert await run_reminders_job(ConsoleMailer()) == ReminderResult()
        async with SessionLocal() as session:
            count = await session.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.stage == "workflow_error")
            )
            assert count >= 1

    asyncio.run(scenario())
