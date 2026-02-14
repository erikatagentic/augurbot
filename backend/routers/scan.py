"""Scan trigger endpoints.

Allows the frontend (or manual curl) to kick off a market scan
as a background task so the HTTP response returns immediately.
"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException

from models.schemas import (
    ManualResolveRequest,
    Platform,
    ResolutionCheckResponse,
    ScanProgressResponse,
    ScanStatusResponse,
)
from services.scanner import execute_scan
from services.scan_progress import get_progress, get_last_scan_summary

logger = logging.getLogger(__name__)

router = APIRouter(tags=["scan"])


@router.get("/scan/progress", response_model=ScanProgressResponse)
async def scan_progress() -> ScanProgressResponse:
    """Get current scan progress (polled by frontend during active scans)."""
    progress = get_progress()

    elapsed = None
    remaining = None
    if progress["started_at"]:
        started = datetime.fromisoformat(progress["started_at"])
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()

        if (
            progress["is_running"]
            and progress["markets_processed"] > 0
            and progress["markets_total"] > 0
        ):
            avg_per_market = elapsed / progress["markets_processed"]
            remaining_markets = progress["markets_total"] - progress["markets_processed"]
            remaining = avg_per_market * remaining_markets

    return ScanProgressResponse(
        **progress,
        elapsed_seconds=round(elapsed, 1) if elapsed is not None else None,
        estimated_remaining_seconds=round(remaining, 1) if remaining is not None else None,
    )


@router.get("/scan/last-summary")
async def last_scan_summary() -> dict:
    """Return summary of the most recent completed scan."""
    return get_last_scan_summary()


@router.post("/scan", response_model=ScanStatusResponse)
async def trigger_full_scan(
    background_tasks: BackgroundTasks,
) -> ScanStatusResponse:
    """Trigger a full scan across all enabled platforms.

    The scan runs as a background task. The response returns
    immediately with ``status="running"``.
    """
    progress = get_progress()
    if progress["is_running"]:
        raise HTTPException(status_code=409, detail="A scan is already running")

    logger.info("Scan endpoint: full scan triggered")
    background_tasks.add_task(execute_scan)

    return ScanStatusResponse(status="running")


@router.post("/scan/{platform}", response_model=ScanStatusResponse)
async def trigger_platform_scan(
    platform: str,
    background_tasks: BackgroundTasks,
) -> ScanStatusResponse:
    """Trigger a scan for a single platform.

    Args:
        platform: Platform name (``polymarket``, ``kalshi``, or ``manifold``).

    Returns:
        ScanStatusResponse with ``status="running"`` and the platform name.

    Raises:
        HTTPException 400: If the platform is not supported.
    """
    valid_platforms = {p.value for p in Platform if p != Platform.metaculus}
    if platform not in valid_platforms:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported platform: {platform}. "
            f"Valid options: {', '.join(sorted(valid_platforms))}",
        )

    progress = get_progress()
    if progress["is_running"]:
        raise HTTPException(status_code=409, detail="A scan is already running")

    logger.info("Scan endpoint: %s scan triggered", platform)
    background_tasks.add_task(execute_scan, platform=platform)

    return ScanStatusResponse(status="running", platform=platform)


@router.post("/resolutions/check", response_model=ResolutionCheckResponse)
async def trigger_resolution_check(
    background_tasks: BackgroundTasks,
) -> ResolutionCheckResponse:
    """Trigger a resolution check across all platforms.

    Checks all active markets for resolution status via platform APIs.
    Runs as a background task — no Claude API calls, zero cost.
    """
    logger.info("Scan endpoint: resolution check triggered")
    background_tasks.add_task(_run_resolution_check)
    return ResolutionCheckResponse(status="running")


async def _run_resolution_check() -> None:
    """Background task wrapper for resolution checking."""
    from services.scanner import check_resolutions

    await check_resolutions()


@router.get("/scan/debug")
async def scan_debug() -> dict:
    """Diagnostic: fetch Kalshi markets and show filter stats without scanning."""
    from services.kalshi import KalshiClient, _is_parlay
    from config import settings
    from models.database import get_config

    db_config = get_config()
    min_volume = db_config.get("min_volume", settings.min_volume)
    max_close_hours = db_config.get("max_close_hours", settings.max_close_hours)

    client = KalshiClient()

    now = datetime.now(timezone.utc)
    min_close = now + timedelta(hours=2)
    max_close = now + timedelta(hours=max_close_hours)
    min_ts = int(min_close.timestamp())
    max_ts = int(max_close.timestamp())

    # Test 1: normal fetch with volume filter + close-date window (mirrors scanner)
    try:
        raw_markets = await client.fetch_markets(
            limit=50,
            min_volume=min_volume,
            min_close_ts=min_ts,
            max_close_ts=max_ts,
        )
    except Exception as exc:
        return {"error": str(exc), "type": type(exc).__name__}

    # Test 2: same close window, $0 volume (see if volume filter is the issue)
    try:
        no_vol_markets = await client.fetch_markets(
            limit=10,
            min_volume=0,
            min_close_ts=min_ts,
            max_close_ts=max_ts,
        )
    except Exception:
        no_vol_markets = []

    # Test 3: wider window (7 days), no volume/category filter
    wide_max_ts = int((now + timedelta(days=7)).timestamp())
    try:
        wide_window_markets = await client.fetch_markets(
            limit=25,
            min_volume=0,
            categories=set(),  # empty = no category filter
            min_close_ts=min_ts,
            max_close_ts=wide_max_ts,
        )
    except Exception:
        wide_window_markets = []

    # Test 4: no close-date filter at all (see what Kalshi returns by default)
    try:
        all_cat_markets = await client.fetch_markets(
            limit=10,
            min_volume=0,
            categories=set(),
        )
    except Exception:
        all_cat_markets = []

    stats = {
        "total_in_window": len(raw_markets),
        "total_no_vol_filter": len(no_vol_markets),
        "total_wide_window_7d": len(wide_window_markets),
        "total_no_date_filter": len(all_cat_markets),
        "min_volume_used": min_volume,
        "max_close_hours": max_close_hours,
        "now_utc": now.isoformat(),
        "min_close": min_close.isoformat(),
        "max_close": max_close.isoformat(),
        "sample_markets": [],
    }

    # Show what's available in the wider 7-day window
    stats["wide_window_sample"] = [
        {
            "q": m.get("question", "")[:80],
            "cat": m.get("category"),
            "vol": m.get("volume"),
            "close": m.get("close_date"),
            "sport": m.get("sport_type"),
        }
        for m in wide_window_markets[:15]
    ]
    stats["no_vol_sample"] = [
        {
            "q": m.get("question", "")[:60],
            "cat": m.get("category"),
            "vol": m.get("volume"),
            "close": m.get("close_date"),
        }
        for m in no_vol_markets[:5]
    ]
    stats["no_date_filter_sample"] = [
        {
            "q": m.get("question", "")[:60],
            "cat": m.get("category"),
            "vol": m.get("volume"),
            "close": m.get("close_date"),
        }
        for m in all_cat_markets[:5]
    ]

    for m in raw_markets[:30]:
        close_str = m.get("close_date")
        hours_away = None
        if close_str:
            try:
                close_dt = datetime.fromisoformat(
                    close_str.replace("Z", "+00:00")
                )
                hours_away = round(
                    (close_dt - now).total_seconds() / 3600, 1
                )
            except (ValueError, TypeError):
                pass
        stats["sample_markets"].append({
            "question": m.get("question", "")[:80],
            "close_date": close_str,
            "hours_until_close": hours_away,
            "volume": m.get("volume"),
            "price_yes": m.get("price_yes"),
            "sport": m.get("sport_type"),
        })

    return stats


@router.post("/markets/{market_id}/resolve")
async def manually_resolve_market(
    market_id: str,
    request: ManualResolveRequest,
) -> dict:
    """Manually resolve a market (for testing or when auto-detection fails).

    Immediately updates market status, closes trades with P&L,
    populates performance_log, and marks recommendations as resolved.
    """
    from models.database import get_market, update_market_status, resolve_recommendations
    from services.scanner import resolve_market_trades

    market = get_market(market_id)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")

    if market.status == "resolved":
        raise HTTPException(status_code=400, detail="Market is already resolved")

    update_market_status(market_id, "resolved", outcome=request.outcome)
    await resolve_market_trades(market_id, request.outcome)
    resolve_recommendations(market_id)

    logger.info(
        "Scan endpoint: manually resolved market %s — outcome=%s",
        market_id,
        "YES" if request.outcome else "NO",
    )

    return {
        "status": "resolved",
        "market_id": market_id,
        "outcome": request.outcome,
    }
