"""Deterministic document-upload reminders and escalation."""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.mail import Mailer, send
from app.models import Request
from app.services.audit import log
from app.services.dispatch import contact_email


@dataclass(frozen=True)
class ReminderResult:
    """Counts returned by a reminder run for API and scheduler evidence."""

    first_reminders: int = 0
    second_reminders: int = 0
    escalations: int = 0


async def run(
    session: AsyncSession, mailer: Mailer, *, now: datetime | None = None
) -> ReminderResult:
    """Send each reminder once, only for outstanding vendor uploads."""

    now = now or datetime.now(UTC)
    requests = (
        await session.scalars(
            select(Request).where(
                Request.documents_clearance == "pending_upload",
                Request.documents_requested_at.is_not(None),
                Request.escalated_at.is_(None),
            )
        )
    ).all()
    first_reminders = second_reminders = escalations = 0
    for request in requests:
        assert request.documents_requested_at is not None
        age_days = (now - request.documents_requested_at).days
        vendor_email = contact_email(request.documentation_contact) or request.requestor_email or ""
        if age_days >= 10:
            await send(
                session,
                mailer,
                request.requestor_email or "",
                "Vendor documents escalation",
                "Required vendor documents remain outstanding after 10 days.",
                "document_escalation",
                request.tracking_id,
            )
            request.escalated_at = now
            await log(
                session,
                request.tracking_id,
                "reminders",
                "escalated",
                "ESCALATE",
                "documents pending upload for at least 10 days",
                "scheduler",
            )
            escalations += 1
        elif age_days >= 7 and request.reminder_count < 2:
            await send(
                session,
                mailer,
                vendor_email,
                "Vendor documents reminder 2",
                "Please upload the outstanding vendor documents.",
                "reminder_2",
                request.tracking_id,
            )
            request.reminder_count = 2
            await log(
                session,
                request.tracking_id,
                "reminders",
                "reminder_2",
                "REMIND",
                "documents pending upload for at least 7 days",
                "scheduler",
            )
            second_reminders += 1
        elif age_days >= 3 and request.reminder_count < 1:
            await send(
                session,
                mailer,
                vendor_email,
                "Vendor documents reminder 1",
                "Please upload the outstanding vendor documents.",
                "reminder_1",
                request.tracking_id,
            )
            request.reminder_count = 1
            await log(
                session,
                request.tracking_id,
                "reminders",
                "reminder_1",
                "REMIND",
                "documents pending upload for at least 3 days",
                "scheduler",
            )
            first_reminders += 1
    return ReminderResult(first_reminders, second_reminders, escalations)
