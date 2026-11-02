"""Dispatch independent Phase 4 human actions without waiting for responses."""

import re
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.mail import Mailer, send
from app.models import Request
from app.services.audit import log
from app.services.requirements import resolve
from app.services.tokens import create

_EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)


def contact_email(contact: str | None) -> str | None:
    """Extract the written contact address without inventing a recipient."""

    match = _EMAIL.search(contact or "")
    return match.group(0) if match else None


async def dispatch(session: AsyncSession, request: Request, mailer: Mailer) -> None:
    """Create action tokens and send every currently-needed notification once."""

    if request.status in {
        "vendor_created",
        "on_hold_compliance",
        "on_hold_duplicate",
        "needs_info",
        "manual_requirements_review",
    }:
        return
    settings = get_settings()
    dispatched: list[str] = []

    if request.financial_clearance == "pending_manager":
        token = await create(session, request.tracking_id, "manager_decision")
        await send(
            session,
            mailer,
            recipient=settings.sourcing_manager_email,
            subject="Vendor onboarding manager decision required",
            body=(
                f"Review request {request.tracking_id}: "
                f"{settings.public_base_url}/forms/manager/{token}"
            ),
            kind="manager_decision",
            tracking_id=request.tracking_id,
        )
        dispatched.append("manager")

    if request.duplicate_clearance == "pending_review":
        token = await create(session, request.tracking_id, "duplicate_review")
        await send(
            session,
            mailer,
            recipient=settings.master_data_email,
            subject="Vendor duplicate review required",
            body=(
                f"Review request {request.tracking_id}: "
                f"{settings.public_base_url}/forms/duplicate/{token}"
            ),
            kind="duplicate_review",
            tracking_id=request.tracking_id,
        )
        dispatched.append("duplicate")

    if request.documents_clearance == "pending_upload" and request.documents_requested_at is None:
        requirements = await resolve(session, request.vendor_country)
        recipient = contact_email(request.documentation_contact)
        if recipient is None:
            request.status = "needs_info"
            await log(
                session,
                request.tracking_id,
                "dispatch",
                "needs_info",
                "HOLD",
                "documentation contact email is unreadable",
                "system",
            )
            return
        token = await create(
            session,
            request.tracking_id,
            "document_upload",
            {"document_types": requirements.document_types},
        )
        checklist = "\n".join(f"- {item}" for item in requirements.document_types)
        await send(
            session,
            mailer,
            recipient=recipient,
            subject="Vendor onboarding documents requested",
            body=(
                f"Please provide:\n{checklist}\n\nUpload link: "
                f"{settings.public_base_url}/forms/documents/{token}"
            ),
            kind="document_request",
            tracking_id=request.tracking_id,
        )
        request.documents_requested_at = datetime.now(UTC)
        dispatched.append("documents")

    if dispatched:
        request.status = "awaiting_actions"
        await log(
            session,
            request.tracking_id,
            "dispatch",
            "awaiting_actions",
            "DISPATCH",
            f"dispatched: {', '.join(dispatched)}",
            "system",
        )
