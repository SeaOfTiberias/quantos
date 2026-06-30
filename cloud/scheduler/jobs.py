"""
QuantOS — Scheduled Jobs
───────────────────────────
US-03: Morning screener job — runs at 8:45 AM IST daily.
Watches a configured path for the day's TradingView CSV export.

Setup options for getting the CSV in place automatically:
  - TradingView's own scheduled export (if available on your plan)
  - A small browser automation script that exports + saves the file
  - Manual drop into the watched folder before 8:45 AM

Run with APScheduler — already in requirements.txt.
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from cloud.api.screener_routes import run_screener_pipeline

logger = logging.getLogger(__name__)

WATCH_PATH = Path(os.getenv("SCREENER_CSV_PATH", "/data/screener_export.csv"))


async def morning_screener_job():
    """
    Scheduled job — runs daily at 8:45 AM IST (03:15 UTC).
    Reads the watched CSV path and runs the full screener pipeline.
    """
    logger.info("Running morning screener job at %s", datetime.now(timezone.utc))

    if not WATCH_PATH.exists():
        logger.warning(
            "No screener CSV found at %s — skipping morning run. "
            "Export from TradingView and place the file there, "
            "or use POST /screener/upload manually.",
            WATCH_PATH,
        )
        return

    try:
        csv_content = WATCH_PATH.read_text(encoding="utf-8")
        result = await run_screener_pipeline(csv_content, send_alert=True)
        logger.info("Morning screener job complete: %s", result)
    except Exception as e:
        logger.error("Morning screener job failed: %s", e)


def register_jobs(scheduler: AsyncIOScheduler) -> None:
    """
    Register all scheduled jobs. Called once at app startup.

    8:45 AM IST = 03:15 UTC
    """
    scheduler.add_job(
        morning_screener_job,
        trigger=CronTrigger(hour=3, minute=15, day_of_week="mon-fri"),
        id="morning_screener",
        name="Morning Screener → Claude Ranker",
        replace_existing=True,
    )
    logger.info("Registered job: morning_screener (8:45 AM IST, Mon-Fri)")
