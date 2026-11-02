"""Optional in-process local scheduler; production replaces it with EventBridge."""

from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import Settings
from app.mail import Mailer
from app.services.jobs import run_reminders_job


def start_scheduler(settings: Settings, mailer: Mailer) -> AsyncIOScheduler | None:
    """Start the daily Dubai reminder schedule only when explicitly enabled."""

    if not settings.scheduler_enabled:
        return None
    scheduler = AsyncIOScheduler(timezone=ZoneInfo(settings.tz))
    scheduler.add_job(run_reminders_job, "cron", hour=9, args=[mailer], id="vendor-reminders")
    scheduler.start()
    return scheduler
