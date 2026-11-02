"""Append-only audit writer."""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def log(
    session: AsyncSession,
    tracking_id: str | None,
    stage: str,
    status: str,
    decision: str,
    reason: str | None,
    actor: str,
    vendor_id: str | None = None,
) -> AuditLog:
    """Append one immutable audit event to the current transaction."""

    event = AuditLog(
        event_id=str(uuid4()),
        tracking_id=tracking_id,
        vendor_id=vendor_id,
        stage=stage,
        status=status,
        decision=decision,
        reason=reason,
        actor=actor,
    )
    session.add(event)
    await session.flush()
    return event
