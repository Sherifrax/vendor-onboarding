"""Phase 1 persistence and core-service checkpoint tests."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import SessionLocal
from app.mail import Mailer, send
from app.models import Request
from app.services.audit import log
from app.services.tokens import consume, create, verify


def unique_id() -> str:
    """Return an isolated stable suffix for database-backed tests."""

    return uuid4().hex


async def create_request(tracking_id: str) -> None:
    """Insert the minimal parent row needed by Phase 1 foreign keys."""

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


def test_audit_log_rejects_update_and_delete() -> None:
    """The database trigger protects audit events beyond application code."""

    async def scenario() -> None:
        async with SessionLocal.begin() as session:
            event = await log(
                session,
                tracking_id=None,
                stage="test",
                status="recorded",
                decision="none",
                reason=None,
                actor="pytest",
            )
            event_id = event.event_id

        async with SessionLocal() as session:
            with pytest.raises(DBAPIError, match="append-only"):
                await session.execute(
                    text("UPDATE audit_log SET status = 'altered' WHERE event_id = :event_id"),
                    {"event_id": event_id},
                )
                await session.commit()
            await session.rollback()
            with pytest.raises(DBAPIError, match="append-only"):
                await session.execute(
                    text("DELETE FROM audit_log WHERE event_id = :event_id"), {"event_id": event_id}
                )
                await session.commit()
            await session.rollback()

    asyncio.run(scenario())


def test_action_tokens_reject_expired_used_and_wrong_purpose() -> None:
    """Token verification is expiry-, purpose-, and single-use-aware."""

    async def scenario() -> None:
        tracking_id = f"VR-token-{unique_id()}"
        await create_request(tracking_id)
        async with SessionLocal.begin() as session:
            expired = await create(session, tracking_id, "manager_decision", ttl_hours=-1)
            used = await create(session, tracking_id, "manager_decision")
            wrong_purpose = await create(session, tracking_id, "manager_decision")

        async with SessionLocal.begin() as session:
            assert await verify(session, expired, "manager_decision") is None
            assert await consume(session, used, "manager_decision") is not None
            assert await verify(session, used, "manager_decision") is None
            assert await verify(session, wrong_purpose, "duplicate_review") is None

    asyncio.run(scenario())


class FailingMailer(Mailer):
    """A transport that fails every attempt while exposing the attempt count."""

    def __init__(self) -> None:
        self.attempts = 0

    async def deliver(self, recipient: str, subject: str, body: str) -> str:
        self.attempts += 1
        raise RuntimeError("transport unavailable")


def test_mail_failure_retries_three_times_and_does_not_raise() -> None:
    """Outbox failure is persisted after precisely three non-throwing attempts."""

    async def scenario() -> None:
        mailer = FailingMailer()
        async with SessionLocal.begin() as session:
            row = await send(
                session,
                mailer,
                recipient="requestor@example.test",
                subject="Phase 1 failure test",
                body="This delivery intentionally fails.",
                kind="test",
                retry_delay_seconds=0,
            )
            assert row.status == "failed"
            assert row.attempts == 3
            assert row.last_error == "transport unavailable"
            assert row.sent_at is None
        assert mailer.attempts == 3

    asyncio.run(scenario())
