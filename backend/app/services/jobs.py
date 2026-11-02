"""Shared job wrapper that records unexpected scheduler failures."""

from app.db import SessionLocal
from app.errors import record_error
from app.mail import Mailer
from app.services.reminders import ReminderResult
from app.services.reminders import run as run_reminders


async def run_reminders_job(mailer: Mailer) -> ReminderResult:
    """Run reminders and return an empty result only after recording a job failure."""

    try:
        async with SessionLocal.begin() as session:
            return await run_reminders(session, mailer)
    except Exception as error:
        await record_error(None, error, mailer)
        return ReminderResult()
