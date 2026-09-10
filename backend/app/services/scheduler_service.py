"""
Reminder Scheduler Service

Thin orchestration layer using APScheduler.
Periodically triggers ReminderService to process due schedules, dispatch notifications,
and handle expired reminders.
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.database import AsyncSessionLocal
from app.services import reminder_service

logger = logging.getLogger(__name__)


class ReminderSchedulerService:
    """
    Orchestrates the periodic execution of ReminderService tasks within FastAPI's event loop.
    """

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._running = False

    def start(self):
        """Start the reminder scheduler cron job."""
        if not self._running:
            self.scheduler.add_job(
                self._run_poll_cycle,
                CronTrigger(second=0),  # Fires at the top of every minute
                id="due_reminders_poller",
                replace_existing=True,
            )
            self.scheduler.start()
            self._running = True
            print("[Scheduler] Reminder scheduler started — polling every 60 seconds")

    def shutdown(self, wait: bool = False):
        """Shutdown the reminder scheduler."""
        if self._running:
            self.scheduler.shutdown(wait=wait)
            self._running = False
            print("[Scheduler] Reminder scheduler stopped")

    async def _run_poll_cycle(self):
        """Execute a single polling cycle via ReminderService."""
        async with AsyncSessionLocal() as session:
            try:
                summary = await reminder_service.poll_and_process_reminders(session)
                await session.commit()
                if summary["created_count"] > 0 or summary["dispatched_count"] > 0 or summary["expired_count"] > 0:
                    print(
                        f"[Scheduler] Polling cycle complete: "
                        f"created={summary['created_count']}, "
                        f"dispatched={summary['dispatched_count']}, "
                        f"expired={summary['expired_count']}"
                    )
            except Exception as e:
                await session.rollback()
                logger.exception(f"[Scheduler] Error during reminder poll cycle: {e}")
                print(f"[Scheduler] Error during reminder poll cycle: {e}")


# Singleton instance
reminder_scheduler = ReminderSchedulerService()

