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
    ScanStatusResponse,
)
from services.scanner import execute_scan

logger = logging.getLogger(__name__)

router = APIRouter(tags=["scan"])


@router.post("/scan", response_model=ScanStatusResponse)
async def trigger_full_scan(
    background_tasks: BackgroundTasks,
) -> ScanStatusResponse:
    """Trigger a full scan across all enabled platforms.

    The scan runs as a background task. The response returns
    immediately with ``status="running"``.
    """
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

    client = KalshiClient()
    try:
        raw_markets = await client.fetch_markets(
            limit=50,
            min_volume=min_volume,
        )
    except Exception as exc:
        return {"error": str(exc), "type": type(exc).__name__}

    now = datetime.now(timezone.utc)
    min_close = now + timedelta(hours=2)
    max_close = now + timedelta(days=30)

    stats = {
        "total_from_kalshi": len(raw_markets),
        "min_volume_used": min_volume,
        "now_utc": now.isoformat(),
        "min_close": min_close.isoformat(),
        "max_close": max_close.isoformat(),
        "passed_filter": 0,
        "too_soon": 0,
        "too_far": 0,
        "no_close_date": 0,
        "sample_markets": [],
    }

    for m in raw_markets[:30]:
        close_str = m.get("close_date")
        sample = {
            "question": m.get("question", "")[:80],
            "close_date": close_str,
            "volume": m.get("volume"),
        }
        if close_str:
            try:
                close_dt = datetime.fromisoformat(
                    close_str.replace("Z", "+00:00")
                )
                hours_away = (close_dt - now).total_seconds() / 3600
                sample["hours_until_close"] = round(hours_away, 1)
                if close_dt < min_close:
                    stats["too_soon"] += 1
                    sample["filter"] = "too_soon"
                elif close_dt > max_close:
                    stats["too_far"] += 1
                    sample["filter"] = "too_far"
                else:
                    stats["passed_filter"] += 1
                    sample["filter"] = "pass"
            except (ValueError, TypeError):
                stats["no_close_date"] += 1
                sample["filter"] = "unparseable"
        else:
            stats["no_close_date"] += 1
            sample["filter"] = "missing"
        stats["sample_markets"].append(sample)

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
