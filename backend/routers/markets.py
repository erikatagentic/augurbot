"""Market browsing and detail endpoints.

Provides market listing, detail views with latest snapshot/estimate,
estimate and snapshot history, and a manual refresh trigger.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from models.schemas import (
    AIEstimateRow,
    BlindMarketInput,
    Confidence,
    MarketDetailResponse,
    MarketListResponse,
    SnapshotRow,
)
from models.database import (
    list_markets,
    count_markets,
    get_market,
    get_latest_snapshot,
    get_latest_estimate,
    get_estimates,
    get_snapshots,
    get_supabase,
    insert_estimate,
    insert_recommendation,
    expire_recommendations,
    close_markets_by_ids,
    close_non_kalshi_markets,
)
from services.researcher import Researcher
from services.calculator import calculate_ev, calculate_kelly, should_recommend

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/markets", tags=["markets"])


@router.get("", response_model=MarketListResponse)
async def get_markets(
    platform: Optional[str] = Query(None, description="Filter by platform"),
    category: Optional[str] = Query(None, description="Filter by category"),
    status: Optional[str] = Query("active", description="Filter by status"),
    limit: int = Query(50, ge=1, le=500, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> MarketListResponse:
    """List tracked markets with optional filters.

    Returns:
        MarketListResponse with the market list and total count.
    """
    markets = list_markets(
        platform=platform,
        category=category,
        status=status,
        limit=limit,
        offset=offset,
    )
    total = count_markets(
        platform=platform,
        category=category,
        status=status,
    )

    return MarketListResponse(markets=markets, total=total)


@router.get("/{market_id}", response_model=MarketDetailResponse)
async def get_market_detail(market_id: str) -> MarketDetailResponse:
    """Get full detail for a single market.

    Includes the latest price snapshot, latest AI estimate, and
    (if available) the latest active recommendation.

    Raises:
        HTTPException 404: If the market does not exist.
    """
    market = get_market(market_id)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")

    snapshot = get_latest_snapshot(market_id)
    estimate = get_latest_estimate(market_id)

    # Look up the latest active recommendation for this market
    from models.database import get_active_recommendations

    latest_rec = None
    active_recs = get_active_recommendations()
    for rec in active_recs:
        if rec.market_id == market_id:
            latest_rec = rec
            break

    return MarketDetailResponse(
        market=market,
        latest_snapshot=snapshot,
        latest_estimate=estimate,
        latest_recommendation=latest_rec,
    )


@router.get("/{market_id}/estimates", response_model=list[AIEstimateRow])
async def get_market_estimates(
    market_id: str,
    limit: int = Query(20, ge=1, le=100),
) -> list[AIEstimateRow]:
    """Get all AI estimates for a market, most recent first.

    Raises:
        HTTPException 404: If the market does not exist.
    """
    market = get_market(market_id)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")

    return get_estimates(market_id, limit=limit)


@router.get("/{market_id}/snapshots", response_model=list[SnapshotRow])
async def get_market_snapshots(
    market_id: str,
    limit: int = Query(100, ge=1, le=500),
) -> list[SnapshotRow]:
    """Get price snapshots for a market, most recent first.

    Raises:
        HTTPException 404: If the market does not exist.
    """
    market = get_market(market_id)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")

    return get_snapshots(market_id, limit=limit)


@router.post("/{market_id}/refresh", response_model=AIEstimateRow)
async def refresh_market_estimate(market_id: str) -> AIEstimateRow:
    """Force a new blind AI estimate for a specific market.

    Uses the high-value model (Opus) since this is a manual/user-triggered
    deep dive. After the estimate is produced, EV is recalculated and
    a recommendation is created if warranted.

    Raises:
        HTTPException 404: If the market does not exist.
        HTTPException 500: If the AI estimation fails.
    """
    market = get_market(market_id)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")

    snapshot = get_latest_snapshot(market_id)

    # Build blind input — NO PRICES
    blind_input = BlindMarketInput(
        question=market.question,
        resolution_criteria=market.resolution_criteria,
        close_date=(
            market.close_date.isoformat() if market.close_date else None
        ),
        category=market.category,
    )

    try:
        researcher = Researcher()
        estimate_output = await researcher.estimate(
            blind_input=blind_input,
            manual=True,  # Force Opus model for manual refresh
        )
    except Exception as exc:
        logger.exception(
            "Market refresh failed for %s: %s", market_id, exc
        )
        raise HTTPException(
            status_code=500,
            detail="AI estimation failed. Please try again later.",
        )

    # Store estimate
    estimate_row = insert_estimate(
        market_id=market.id,
        probability=estimate_output.probability,
        confidence=estimate_output.confidence.value,
        reasoning=estimate_output.reasoning,
        key_evidence=estimate_output.key_evidence,
        key_uncertainties=estimate_output.key_uncertainties,
        model_used=researcher._select_model(manual=True),
    )

    # Recalculate EV if we have a snapshot
    if snapshot is not None:
        ev_result = calculate_ev(
            ai_probability=estimate_output.probability,
            market_price=snapshot.price_yes,
            platform=market.platform,
        )

        if ev_result is not None and should_recommend(ev_result["ev"]):
            kelly = calculate_kelly(
                edge=ev_result["edge"],
                market_price=snapshot.price_yes,
                direction=ev_result["direction"],
                confidence=Confidence(estimate_output.confidence.value),
            )

            expire_recommendations(market.id)

            insert_recommendation(
                market_id=market.id,
                estimate_id=estimate_row.id,
                snapshot_id=snapshot.id,
                direction=ev_result["direction"],
                market_price=snapshot.price_yes,
                ai_probability=estimate_output.probability,
                edge=ev_result["edge"],
                ev=ev_result["ev"],
                kelly_fraction=kelly,
            )

    return estimate_row


@router.post("/admin/cleanup")
async def cleanup_garbled_markets(
    dry_run: bool = Query(True, description="Preview only; set false to execute"),
) -> dict:
    """Remove garbled parlay markets and close non-Kalshi markets.

    Uses the same ``_is_parlay()`` heuristic as the scanner to detect
    comma-separated combo titles.  Also marks Polymarket/Manifold
    markets as closed since the app is now Kalshi-only.

    Args:
        dry_run: If True (default), returns what *would* be cleaned
                 without modifying the database.
    """
    from services.kalshi import _is_parlay

    # Find garbled Kalshi parlays
    all_kalshi = list_markets(platform="kalshi", status="active", limit=500)
    parlay_ids: list[str] = []
    parlay_titles: list[str] = []
    for m in all_kalshi:
        if _is_parlay({"title": m.question}):
            parlay_ids.append(m.id)
            parlay_titles.append(m.question[:80])

    # Count non-Kalshi active markets
    non_kalshi_count = (
        count_markets(platform="polymarket", status="active")
        + count_markets(platform="manifold", status="active")
    )

    result = {
        "parlay_markets_found": len(parlay_ids),
        "parlay_titles": parlay_titles,
        "non_kalshi_active": non_kalshi_count,
        "dry_run": dry_run,
    }

    if not dry_run:
        try:
            parlays_closed = close_markets_by_ids(parlay_ids)
            result["parlays_closed"] = parlays_closed
        except Exception as exc:
            logger.exception("Cleanup: parlay close failed")
            result["parlay_close_error"] = str(exc)

        try:
            closed = close_non_kalshi_markets()
            result["non_kalshi_closed"] = closed
        except Exception as exc:
            logger.exception("Cleanup: non-Kalshi close failed")
            result["non_kalshi_close_error"] = str(exc)

        logger.info("Cleanup completed: %s", result)

    return result


@router.post("/admin/backfill-labels")
async def backfill_outcome_labels() -> dict:
    """Backfill outcome_label from description for markets missing it."""
    db = get_supabase()
    result = (
        db.table("markets")
        .select("id, description")
        .is_("outcome_label", "null")
        .execute()
    )
    updated = 0
    for row in result.data:
        desc = row.get("description") or ""
        if desc.startswith("If ") and " wins the " in desc:
            label = desc[3:desc.index(" wins the ")]
            db.table("markets").update({"outcome_label": label}).eq("id", row["id"]).execute()
            updated += 1
    return {"markets_checked": len(result.data), "labels_updated": updated}
