"""Pipeline orchestrator — scans markets, runs blind AI research, calculates EV.

This module coordinates the full scan pipeline:
  1. Fetch markets from platform clients
  2. Upsert market metadata and snapshot prices
  3. Run blind AI estimation (no prices exposed to Claude)
  4. Compare AI estimate to market price and generate recommendations

Uses asyncio.Semaphore to limit concurrent Claude API calls.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from config import settings
from models.schemas import (
    BlindMarketInput,
    Confidence,
    Platform,
    ScanStatusResponse,
)
from models.database import (
    upsert_market,
    insert_snapshot,
    get_latest_estimate,
    insert_estimate,
    insert_recommendation,
    insert_performance,
    insert_cost_log,
    expire_recommendations,
    resolve_recommendations,
    cancel_trades_for_market,
    get_markets_with_price_movement,
    get_latest_snapshot,
    close_trades_for_market,
    list_markets,
    update_market_status,
)
from services.polymarket import PolymarketClient
from services.kalshi import KalshiClient
from services.manifold import ManifoldClient
from services.researcher import Researcher
from services.calculator import (
    calculate_ev,
    calculate_kelly,
    calculate_brier_score,
    should_recommend,
)

logger = logging.getLogger(__name__)

# Limit concurrent Claude API calls to avoid rate-limiting / cost spikes
_claude_semaphore = asyncio.Semaphore(3)


def _get_platform_client(platform: str):
    """Instantiate the correct platform client.

    Args:
        platform: One of ``"polymarket"``, ``"kalshi"``, ``"manifold"``.

    Returns:
        Platform client instance.

    Raises:
        ValueError: If the platform is not supported.
    """
    if platform == Platform.polymarket.value:
        return PolymarketClient()
    elif platform == Platform.kalshi.value:
        return KalshiClient()
    elif platform == Platform.manifold.value:
        return ManifoldClient()
    else:
        raise ValueError(f"Unsupported platform: {platform}")


def _needs_research(market_id: str, max_age_hours: float = 6.0) -> bool:
    """Check whether a market needs a new AI estimate.

    Returns ``True`` if there is no existing estimate or the most recent
    estimate is older than ``max_age_hours``.

    Args:
        market_id: Internal market UUID.
        max_age_hours: Maximum age of the latest estimate before
                       re-research is triggered.

    Returns:
        Whether the market should be queued for AI research.
    """
    latest = get_latest_estimate(market_id)
    if latest is None:
        return True

    age = datetime.now(timezone.utc) - latest.created_at.replace(
        tzinfo=timezone.utc
    )
    return age > timedelta(hours=max_age_hours)


async def _process_market(
    market_data: dict,
    researcher: Researcher,
    scan_id: str | None = None,
) -> Optional[str]:
    """Process a single market through the full pipeline.

    Steps:
      1. Upsert market metadata into the database.
      2. Insert a price snapshot.
      3. Check whether AI research is needed (skip if recent estimate exists).
      4. Build a BlindMarketInput (NO prices, NO volume).
      5. Call the researcher to get a probability estimate.
      6. Store the estimate.
      7. Compare estimate to market price and create a recommendation if EV is sufficient.

    Args:
        market_data: Normalized market dict from a platform client.
        researcher: Researcher instance for Claude API calls.

    Returns:
        ``"researched"`` if a new estimate was produced,
        ``"recommended"`` if a recommendation was also created,
        ``"skipped"`` if research was not needed,
        or ``None`` on error.
    """
    platform = market_data["platform"]
    platform_id = market_data["platform_id"]

    try:
        # Step 1: Upsert market metadata
        market_row = upsert_market(
            platform=platform,
            platform_id=platform_id,
            question=market_data["question"],
            description=market_data.get("description"),
            resolution_criteria=market_data.get("resolution_criteria"),
            category=market_data.get("category"),
            close_date=market_data.get("close_date"),
        )

        # Step 2: Insert price snapshot
        snapshot = insert_snapshot(
            market_id=market_row.id,
            price_yes=market_data.get("price_yes", 0.5),
            price_no=market_data.get("price_no"),
            volume=market_data.get("volume"),
            liquidity=market_data.get("liquidity"),
        )

        # Step 3: Check if research is needed
        if not _needs_research(market_row.id, max_age_hours=settings.estimate_cache_hours):
            logger.debug(
                "Scanner: skipping '%s' — recent estimate exists",
                market_data["question"][:60],
            )
            return "skipped"

        # Step 4: Build blind input — NO PRICES, NO VOLUME
        blind_input = BlindMarketInput(
            question=market_data["question"],
            resolution_criteria=market_data.get("resolution_criteria"),
            close_date=market_data.get("close_date"),
            category=market_data.get("category"),
        )

        # Step 5: Call researcher (volume used ONLY for model selection)
        async with _claude_semaphore:
            estimate_output = await researcher.estimate(
                blind_input=blind_input,
                volume=market_data.get("volume"),
            )

        # Step 6: Store estimate
        model_used = researcher._select_model(
            volume=market_data.get("volume")
        )
        estimate_row = insert_estimate(
            market_id=market_row.id,
            probability=estimate_output.probability,
            confidence=estimate_output.confidence.value,
            reasoning=estimate_output.reasoning,
            key_evidence=estimate_output.key_evidence,
            key_uncertainties=estimate_output.key_uncertainties,
            model_used=model_used,
        )

        # Step 6b: Log cost
        if estimate_output.estimated_cost > 0:
            try:
                insert_cost_log(
                    model_used=model_used,
                    input_tokens=estimate_output.input_tokens,
                    output_tokens=estimate_output.output_tokens,
                    estimated_cost=estimate_output.estimated_cost,
                    scan_id=scan_id,
                    market_id=market_row.id,
                )
            except Exception:
                logger.debug("Scanner: failed to log cost for %s", market_row.id)

        # Step 7: ONLY NOW use prices — compare AI estimate to market price
        ev_result = calculate_ev(
            ai_probability=estimate_output.probability,
            market_price=snapshot.price_yes,
            platform=platform,
        )

        if ev_result is not None and should_recommend(ev_result["ev"]):
            # Calculate Kelly fraction
            kelly = calculate_kelly(
                edge=ev_result["edge"],
                market_price=snapshot.price_yes,
                direction=ev_result["direction"],
                confidence=Confidence(estimate_output.confidence.value),
            )

            # Expire any old active recommendations for this market
            expire_recommendations(market_row.id)

            # Insert new recommendation
            insert_recommendation(
                market_id=market_row.id,
                estimate_id=estimate_row.id,
                snapshot_id=snapshot.id,
                direction=ev_result["direction"],
                market_price=snapshot.price_yes,
                ai_probability=estimate_output.probability,
                edge=ev_result["edge"],
                ev=ev_result["ev"],
                kelly_fraction=kelly,
            )

            logger.info(
                "Scanner: recommendation created for '%s' — "
                "direction=%s edge=%.2f%% ev=%.2f%%",
                market_data["question"][:60],
                ev_result["direction"],
                ev_result["edge"] * 100,
                ev_result["ev"] * 100,
            )
            return "recommended"

        return "researched"

    except Exception:
        logger.exception(
            "Scanner: error processing market '%s' on %s",
            market_data.get("question", "unknown")[:60],
            platform,
        )
        return None


async def execute_scan(
    platform: Optional[str] = None,
) -> ScanStatusResponse:
    """Execute a full market scan across one or all platforms.

    For each enabled platform:
      1. Fetch active markets from the platform API.
      2. Process each market through the blind estimation pipeline.

    Args:
        platform: If provided, scan only this platform.
                  Otherwise scan all enabled platforms.

    Returns:
        ScanStatusResponse with summary statistics.
    """
    started_at = datetime.now(timezone.utc)
    scan_id = str(uuid.uuid4())
    researcher = Researcher()

    # Determine which platforms to scan
    if platform:
        platforms = [platform]
    else:
        platforms = []
        platforms.append(Platform.polymarket.value)
        platforms.append(Platform.manifold.value)
        if settings.kalshi_email and settings.kalshi_password:
            platforms.append(Platform.kalshi.value)

    markets_found = 0
    markets_researched = 0
    recommendations_created = 0

    for plat in platforms:
        try:
            client = _get_platform_client(plat)

            logger.info("Scanner: fetching markets from %s", plat)
            market_list = await client.fetch_markets(
                limit=settings.markets_per_platform,
                min_volume=settings.min_volume,
            )
            markets_found += len(market_list)

            logger.info(
                "Scanner: processing %d markets from %s",
                len(market_list),
                plat,
            )

            # Process markets concurrently (bounded by semaphore)
            tasks = [
                _process_market(m, researcher, scan_id=scan_id) for m in market_list
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    logger.error(
                        "Scanner: task exception during %s scan: %s",
                        plat,
                        result,
                    )
                    continue
                if result == "researched":
                    markets_researched += 1
                elif result == "recommended":
                    markets_researched += 1
                    recommendations_created += 1

        except Exception:
            logger.exception("Scanner: failed to scan platform %s", plat)

    completed_at = datetime.now(timezone.utc)

    logger.info(
        "Scanner: scan complete — found=%d researched=%d recommended=%d "
        "duration=%.1fs",
        markets_found,
        markets_researched,
        recommendations_created,
        (completed_at - started_at).total_seconds(),
    )

    return ScanStatusResponse(
        status="completed",
        platform=platform,
        markets_found=markets_found,
        markets_researched=markets_researched,
        recommendations_created=recommendations_created,
        started_at=started_at,
        completed_at=completed_at,
    )


async def check_and_reestimate() -> int:
    """Re-estimate markets where the price has moved significantly.

    Finds active markets where the latest two snapshots differ by more
    than ``settings.re_estimate_trigger`` and runs a new blind estimate
    for each.

    Returns:
        Number of markets that were re-estimated.
    """
    threshold = settings.re_estimate_trigger
    moved_markets = get_markets_with_price_movement(threshold=threshold)

    if not moved_markets:
        logger.info(
            "Scanner: no markets with price movement > %.1f%%",
            threshold * 100,
        )
        return 0

    logger.info(
        "Scanner: %d markets with significant price movement, re-estimating",
        len(moved_markets),
    )

    researcher = Researcher()
    re_estimated = 0

    for market_row, old_snapshot, new_snapshot in moved_markets:
        try:
            # Build blind input — NO PRICES
            blind_input = BlindMarketInput(
                question=market_row.question,
                resolution_criteria=market_row.resolution_criteria,
                close_date=(
                    market_row.close_date.isoformat()
                    if market_row.close_date
                    else None
                ),
                category=market_row.category,
            )

            # Get volume from latest snapshot for model selection only
            volume = new_snapshot.volume

            async with _claude_semaphore:
                estimate_output = await researcher.estimate(
                    blind_input=blind_input,
                    volume=volume,
                )

            # Store estimate
            estimate_row = insert_estimate(
                market_id=market_row.id,
                probability=estimate_output.probability,
                confidence=estimate_output.confidence.value,
                reasoning=estimate_output.reasoning,
                key_evidence=estimate_output.key_evidence,
                key_uncertainties=estimate_output.key_uncertainties,
                model_used=researcher._select_model(volume=volume),
            )

            # Recalculate EV with fresh snapshot price
            ev_result = calculate_ev(
                ai_probability=estimate_output.probability,
                market_price=new_snapshot.price_yes,
                platform=market_row.platform,
            )

            if ev_result is not None and should_recommend(ev_result["ev"]):
                kelly = calculate_kelly(
                    edge=ev_result["edge"],
                    market_price=new_snapshot.price_yes,
                    direction=ev_result["direction"],
                    confidence=Confidence(estimate_output.confidence.value),
                )

                expire_recommendations(market_row.id)

                insert_recommendation(
                    market_id=market_row.id,
                    estimate_id=estimate_row.id,
                    snapshot_id=new_snapshot.id,
                    direction=ev_result["direction"],
                    market_price=new_snapshot.price_yes,
                    ai_probability=estimate_output.probability,
                    edge=ev_result["edge"],
                    ev=ev_result["ev"],
                    kelly_fraction=kelly,
                )

            re_estimated += 1

            logger.info(
                "Scanner: re-estimated '%s' — price moved %.1f%% -> %.1f%%",
                market_row.question[:60],
                old_snapshot.price_yes * 100,
                new_snapshot.price_yes * 100,
            )

        except Exception:
            logger.exception(
                "Scanner: error re-estimating market %s",
                market_row.id,
            )

    logger.info("Scanner: re-estimated %d markets", re_estimated)
    return re_estimated


async def resolve_market_trades(market_id: str, outcome: bool) -> None:
    """Close all open trades for a resolved market and populate performance_log.

    Called when a market resolution is detected (future: auto-detection via
    platform APIs). Closes all open trades, calculates P&L, and records the
    AI's calibration data in the performance_log table.

    Args:
        market_id: ID of the resolved market.
        outcome: True if YES resolved, False if NO resolved.
    """
    exit_price = 1.0 if outcome else 0.0
    closed_trades = close_trades_for_market(market_id, exit_price)

    estimate = get_latest_estimate(market_id)
    snapshot = get_latest_snapshot(market_id)

    if estimate and snapshot:
        brier = calculate_brier_score(estimate.probability, outcome)
        total_pnl = sum(t.pnl or 0 for t in closed_trades)

        insert_performance(
            market_id=market_id,
            ai_probability=estimate.probability,
            market_price=snapshot.price_yes,
            actual_outcome=outcome,
            brier_score=brier,
            pnl=total_pnl if closed_trades else None,
        )

    logger.info(
        "Scanner: resolved market %s — outcome=%s, closed %d trades",
        market_id,
        outcome,
        len(closed_trades),
    )


async def check_resolutions() -> dict:
    """Check all active markets for resolution status via platform APIs.

    For each platform, queries the platform API for every active market in the
    database. When a market has resolved, it triggers the downstream pipeline:
    update status, close trades, calculate P&L, populate performance_log.

    This function makes NO Claude API calls — only platform HTTP reads.

    Returns:
        Summary dict with markets_checked, markets_resolved, markets_cancelled.
    """
    platforms_to_check = [Platform.polymarket.value, Platform.manifold.value]
    if settings.kalshi_email and settings.kalshi_password:
        platforms_to_check.append(Platform.kalshi.value)

    total_checked = 0
    total_resolved = 0
    total_cancelled = 0

    for plat in platforms_to_check:
        try:
            active_markets = list_markets(platform=plat, status="active", limit=500)
            if not active_markets:
                continue

            client = _get_platform_client(plat)
            platform_ids = [m.platform_id for m in active_markets]
            market_lookup = {m.platform_id: m for m in active_markets}

            logger.info(
                "Resolution: checking %d active %s markets",
                len(platform_ids),
                plat,
            )

            results = await client.check_resolutions_batch(platform_ids)
            total_checked += len(results)

            for platform_id, resolution in results.items():
                market_row = market_lookup.get(platform_id)
                if market_row is None:
                    continue

                if resolution.get("cancelled"):
                    update_market_status(market_row.id, "closed")
                    expire_recommendations(market_row.id)
                    cancel_trades_for_market(market_row.id)
                    total_cancelled += 1
                    logger.info(
                        "Resolution: '%s' cancelled on %s",
                        market_row.question[:60],
                        plat,
                    )

                elif resolution.get("resolved") and resolution.get("outcome") is not None:
                    outcome = resolution["outcome"]
                    update_market_status(market_row.id, "resolved", outcome=outcome)
                    await resolve_market_trades(market_row.id, outcome)
                    resolve_recommendations(market_row.id)
                    total_resolved += 1
                    logger.info(
                        "Resolution: '%s' resolved %s on %s",
                        market_row.question[:60],
                        "YES" if outcome else "NO",
                        plat,
                    )

        except Exception:
            logger.exception("Resolution check failed for platform %s", plat)

    logger.info(
        "Resolution check complete: checked=%d resolved=%d cancelled=%d",
        total_checked,
        total_resolved,
        total_cancelled,
    )

    return {
        "markets_checked": total_checked,
        "markets_resolved": total_resolved,
        "markets_cancelled": total_cancelled,
    }
