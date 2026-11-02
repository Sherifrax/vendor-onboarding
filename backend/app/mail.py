"""Outbound mail interface with durable outbox and retry."""

import asyncio
from abc import ABC, abstractmethod
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EmailOutbox

MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 5


class Mailer(ABC):
    """Transport abstraction for outbound notifications."""

    @abstractmethod
    async def deliver(self, recipient: str, subject: str, body: str) -> str:
        """Deliver one message and return its transport message identifier."""


class ConsoleMailer(Mailer):
    async def deliver(self, recipient: str, subject: str, body: str) -> str:
        return f"console-{datetime.now(UTC).timestamp()}"


async def send(
    session: AsyncSession,
    mailer: Mailer,
    recipient: str,
    subject: str,
    body: str,
    kind: str,
    tracking_id: str | None = None,
    retry_delay_seconds: float = RETRY_DELAY_SECONDS,
) -> EmailOutbox:
    """Record and attempt delivery, preserving failure as durable outbox state."""

    row = EmailOutbox(
        tracking_id=tracking_id,
        recipient=recipient,
        subject=subject,
        body=body,
        kind=kind,
        status="pending",
        attempts=0,
    )
    session.add(row)
    await session.flush()
    for attempt in range(MAX_ATTEMPTS):
        row.attempts += 1
        try:
            row.message_id = await mailer.deliver(recipient, subject, body)
            row.status = "sent"
            row.sent_at = datetime.now(UTC)
            break
        except Exception as error:  # Delivery must never break the workflow.
            row.last_error = str(error)
            row.status = "failed"
            if attempt < MAX_ATTEMPTS - 1:
                await asyncio.sleep(retry_delay_seconds)
    await session.flush()
    return row
