from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timezone
import logging
import traceback
from typing import Dict, Any
from supabase._async.client import AsyncClient
from app.services.timeline_recap_services import schedule_daily_recaps_update, schedule_weekly_recaps_update

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pillar.scheduler")

# Global scheduler instance
scheduler = AsyncIOScheduler(timezone=timezone.utc)


def init_scheduler(supabase: AsyncClient) -> None:
    """
    Initialize the scheduler and add jobs.

    According to the requirements, we need to:
    - Run daily updates at 8:00am UTC every day
    - Run weekly updates on Mondays at 8:00am UTC
    """
    logger.info("Initializing scheduler...")

    # Daily recap at 8:00am UTC every day
    scheduler.add_job(
        schedule_daily_recaps_update,
        CronTrigger(hour=8, minute=0),
        args=[supabase],
        id="daily_recap_update",
        replace_existing=True,
        misfire_grace_time=3600,  # Allow up to 1 hour of misfire grace time
    )

    # Weekly recap at 8:00am UTC every Monday
    scheduler.add_job(
        schedule_weekly_recaps_update,
        CronTrigger(day_of_week="mon", hour=8, minute=0),
        args=[supabase],
        id="weekly_recap_update",
        replace_existing=True,
        misfire_grace_time=3600,  # Allow up to 1 hour of misfire grace time
    )

    # Start the scheduler
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started successfully")


def shutdown_scheduler() -> None:
    """Shut down the scheduler"""
    scheduler.shutdown()
    logger.info("Scheduler shut down successfully")
