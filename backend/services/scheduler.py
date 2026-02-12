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


def configure_scheduler() -> None:
    """Add the recurring scan and price-check jobs to the scheduler.

    Call this once during application startup (before ``scheduler.start()``).
    """
    # Full scan: daily at 8 AM Pacific
    scheduler.add_job(
        run_full_scan,
        trigger=CronTrigger(hour=8, minute=0, timezone=SCAN_TIMEZONE),
        id="full_scan",
        name="Full market scan (daily 8 AM PT)",
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

    # Trade sync: sync positions/fills from Polymarket + Kalshi
    if settings.trade_sync_enabled:
        scheduler.add_job(
            sync_platform_trades,
            trigger=IntervalTrigger(hours=settings.trade_sync_interval_hours),
            id="trade_sync",
            name="Trade sync from platforms",
            replace_existing=True,
            max_instances=1,
        )

    logger.info(
        "Scheduler: configured — full scan daily 8 AM PT, price check %s, resolution check %s, trade sync %s",
        f"every {settings.price_check_interval_hours}h"
        if settings.price_check_enabled
        else "disabled",
        f"every {settings.resolution_check_interval_hours}h"
        if settings.resolution_check_enabled
        else "disabled",
        f"every {settings.trade_sync_interval_hours}h"
        if settings.trade_sync_enabled
        else "disabled",
    )
