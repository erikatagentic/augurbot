"""APScheduler configuration for periodic market scanning.

Defines two recurring jobs:
  - ``full_scan``: runs the complete scan pipeline every N hours
    (configured via ``settings.scan_interval_hours``).
  - ``price_check``: checks for significant price movements every 1 hour
    and triggers re-estimation when a market moves more than the
    configured threshold.

Uses deferred imports inside job functions to avoid circular imports
between the scheduler and the scanner module.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import settings

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

        result = await execute_scan()
        logger.info(
            "Scheduler: full scan completed — found=%d researched=%d recommended=%d",
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


def configure_scheduler() -> None:
    """Add the recurring scan and price-check jobs to the scheduler.

    Call this once during application startup (before ``scheduler.start()``).
    """
    # Full scan: run every scan_interval_hours (default 24)
    scheduler.add_job(
        run_full_scan,
        trigger=IntervalTrigger(hours=settings.scan_interval_hours),
        id="full_scan",
        name="Full market scan",
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

    logger.info(
        "Scheduler: configured — full scan every %dh, price check %s",
        settings.scan_interval_hours,
        f"every {settings.price_check_interval_hours}h"
        if settings.price_check_enabled
        else "disabled",
    )
