"""Fail-soft error alerts and immutable workflow error events."""

import traceback

from app.config import get_settings
from app.db import SessionLocal
from app.mail import Mailer, send
from app.services.audit import log


def error_summary(error: Exception) -> str:
    """Return a bounded stack summary without request bodies or secrets."""

    return "".join(traceback.format_exception_only(type(error), error)).strip()[:1_000]


async def record_error(tracking_id: str | None, error: Exception, mailer: Mailer) -> None:
    """Attempt alert and audit independently so either failure cannot block the other."""

    summary = error_summary(error)
    try:
        async with SessionLocal.begin() as session:
            await send(
                session,
                mailer,
                get_settings().owner_alert_email,
                "Vendor onboarding workflow error",
                f"Request: {tracking_id or 'unknown'}\nError: {summary}",
                "workflow_error_alert",
                tracking_id,
            )
    except Exception:
        pass
    try:
        async with SessionLocal.begin() as session:
            await log(
                session,
                tracking_id,
                "workflow_error",
                "ERROR",
                "HOLD",
                summary,
                "system",
            )
    except Exception:
        pass
