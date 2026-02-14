"""APScheduler configuration for periodic market scanning.

Defines recurring jobs:
  - ``full_scan``: runs the complete scan pipeline at configured hours
    (default 8 AM + 2 PM Pacific, configurable via Settings UI).
  - ``price_check``: checks for significant price movements and triggers
    re-estimation when a market moves more than the configured threshold.
  - ``resolution_check``: polls platform APIs for resolved markets.
  - ``trade_sync``: syncs positions from connected platforms.
  - ``daily_digest``: sends nightly email/Slack summary.

Uses deferred imports inside job functions to avoid circular imports
between the scheduler and the scanner module.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import settings

SCAN_TIMEZONE = ZoneInfo("America/Los_Angeles")

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def run_full_scan() -> None:
    """Execute a full market scan across all enabled platforms.

    Catches and logs all exceptions so that one failed run does not
    crash the scheduler.
    """
    logger.info("Scheduler: starting full market scan")
    try:
        # Deferred import to avoid circular dependency
        from services.scanner import execute_scan

        result = await execute_scan(use_batch=True)
        logger.info(
            "Scheduler: full scan completed (batch) — found=%d researched=%d recommended=%d",
            result.markets_found,
            result.markets_researched,
            result.recommendations_created,
        )
    except Exception:
        logger.exception("Scheduler: full scan failed")


async def check_price_movements() -> None:
    """Check for significant price movements and trigger re-estimation.

    Catches and logs all exceptions so that one failed run does not
    crash the scheduler.
    """
    logger.info("Scheduler: checking for price movements")
    try:
        # Deferred import to avoid circular dependency
        from services.scanner import check_and_reestimate

        count = await check_and_reestimate()
        logger.info(
            "Scheduler: price movement check complete — re-estimated %d markets",
            count,
        )
    except Exception:
        logger.exception("Scheduler: price movement check failed")


async def sync_platform_trades() -> None:
    """Sync trades from connected platform accounts.

    Fetches positions/fills from Polymarket and Kalshi, inserts new trades.
    Catches and logs all exceptions so that one failed run does not
    crash the scheduler.
    """
    logger.info("Scheduler: starting trade sync")
    try:
        from services.trade_syncer import sync_all_trades

        result = await sync_all_trades()
        logger.info("Scheduler: trade sync completed — %s", result)
    except Exception:
        logger.exception("Scheduler: trade sync failed")


async def check_market_resolutions() -> None:
    """Check all tracked markets for resolution and process resolved ones.

    Catches and logs all exceptions so that one failed run does not
    crash the scheduler.
    """
    logger.info("Scheduler: starting resolution check")
    try:
        # Deferred import to avoid circular dependency
        from services.scanner import check_resolutions

        result = await check_resolutions()
        logger.info(
            "Scheduler: resolution check completed — checked=%d resolved=%d cancelled=%d",
            result["markets_checked"],
            result["markets_resolved"],
            result["markets_cancelled"],
        )
    except Exception:
        logger.exception("Scheduler: resolution check failed")


def get_next_scan_time() -> Optional[datetime]:
    """Return the next scheduled full scan time (UTC)."""
    job = scheduler.get_job("full_scan")
    if job and job.next_run_time:
        return job.next_run_time.astimezone(timezone.utc)
    return None


async def send_daily_digest_job() -> None:
    """Send daily digest email/Slack summary at 9 PM PT."""
    logger.info("Scheduler: sending daily digest")
    try:
        from services.notifier import send_daily_digest

        result = await send_daily_digest()
        logger.info("Scheduler: daily digest sent — %s", result)
    except Exception:
        logger.exception("Scheduler: daily digest failed")


def _build_scan_hour_str(scan_times: list[int]) -> str:
    """Validate and build a comma-separated hour string for CronTrigger."""
    valid = sorted(h for h in scan_times if 0 <= h <= 23)
    if not valid:
        valid = [8, 14]
    return ",".join(str(h) for h in valid)


def reconfigure_scan_schedule(scan_times: list[int]) -> None:
    """Update the running scan schedule to the specified hours (Pacific Time).

    Uses APScheduler's ``reschedule_job`` to atomically replace the trigger.
    ``max_instances=1`` (set at job creation) prevents overlapping runs.
    ``get_next_scan_time()`` auto-updates since it reads from the job object.
    """
    if not scan_times:
        logger.warning("Scheduler: empty scan_times, keeping existing schedule")
        return

    hour_str = _build_scan_hour_str(scan_times)

    scheduler.reschedule_job(
        "full_scan",
        trigger=CronTrigger(hour=hour_str, minute=0, timezone=SCAN_TIMEZONE),
    )

    labels = [
        f"{h % 12 or 12} {'AM' if h < 12 else 'PM'}"
        for h in sorted(int(x) for x in hour_str.split(","))
    ]
    logger.info("Scheduler: scan schedule updated to %s PT", ", ".join(labels))


def configure_scheduler() -> None:
    """Add the recurring scan and price-check jobs to the scheduler.

    Call this once during application startup (before ``scheduler.start()``).
    Reads ``scan_times`` from the database config so user-configured
    schedules survive restarts.
    """
    # Read DB config for user-configured scan_times
    from models.database import get_config

    db_config = get_config()
    scan_times = db_config.get("scan_times", settings.scan_times)
    hour_str = _build_scan_hour_str(scan_times)

    # Full scan: at configured hours Pacific
    scheduler.add_job(
        run_full_scan,
        trigger=CronTrigger(hour=hour_str, minute=0, timezone=SCAN_TIMEZONE),
        id="full_scan",
        name=f"Full market scan ({hour_str} PT)",
        replace_existing=True,
        max_instances=1,
    )

    # Price movement check: configurable, disabled by default
    if settings.price_check_enabled:
        scheduler.add_job(
            check_price_movements,
            trigger=IntervalTrigger(hours=settings.price_check_interval_hours),
            id="price_check",
            name="Price movement check",
            replace_existing=True,
            max_instances=1,
        )

    # Resolution check: run every N hours (free — no Claude API calls)
    if settings.resolution_check_enabled:
        scheduler.add_job(
            check_market_resolutions,
            trigger=IntervalTrigger(hours=settings.resolution_check_interval_hours),
            id="resolution_check",
            name="Market resolution check",
            replace_existing=True,
            max_instances=1,
        )

    # Trade sync: sync positions/fills from Kalshi
    if settings.trade_sync_enabled:
        scheduler.add_job(
            sync_platform_trades,
            trigger=IntervalTrigger(hours=settings.trade_sync_interval_hours),
            id="trade_sync",
            name="Trade sync from platforms",
            replace_existing=True,
            max_instances=1,
        )

    # Daily digest: 9 PM PT
    if settings.notifications_enabled:
        scheduler.add_job(
            send_daily_digest_job,
            trigger=CronTrigger(hour=21, minute=0, timezone=SCAN_TIMEZONE),
            id="daily_digest",
            name="Daily digest (9 PM PT)",
            replace_existing=True,
            max_instances=1,
        )

    scan_label = ", ".join(
        f"{h % 12 or 12} {'AM' if h < 12 else 'PM'}"
        for h in sorted(int(x) for x in hour_str.split(","))
    )
    logger.info(
        "Scheduler: configured — scan at %s PT, price check %s, resolution check %s, trade sync %s, digest %s",
        scan_label,
        f"every {settings.price_check_interval_hours}h"
        if settings.price_check_enabled
        else "disabled",
        f"every {settings.resolution_check_interval_hours}h"
        if settings.resolution_check_enabled
        else "disabled",
        f"every {settings.trade_sync_interval_hours}h"
        if settings.trade_sync_enabled
        else "disabled",
        "9 PM PT" if settings.notifications_enabled else "disabled",
    )
