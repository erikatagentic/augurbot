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
    PreparedMarket,
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
    get_config,
    get_calibration_feedback,
    get_active_recommendations,
    get_untraded_active_recommendations,
    get_market,
    get_recommendation_for_market,
    insert_trade,
)
from services.polymarket import PolymarketClient
from services.kalshi import KalshiClient
from services.manifold import ManifoldClient
from services.researcher import Researcher
from services.notifier import send_scan_notifications
from services.calculator import (
    calculate_ev,
    calculate_kelly,
    calculate_brier_score,
    calculate_pnl,
    should_recommend,
)
from services.scan_progress import (
    start_scan,
    set_markets_found,
    market_processing,
    market_done,
    complete_scan,
    fail_scan,
    save_scan_summary,
    update_batch_status,
)

logger = logging.getLogger(__name__)

# Limit concurrent Claude API calls to avoid rate-limiting / cost spikes
_claude_semaphore = asyncio.Semaphore(5)


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


async def _prepare_market(
    market_data: dict,
    researcher: Researcher,
    scan_id: str | None = None,
) -> Optional[PreparedMarket]:
    """Prepare a market for AI estimation (steps 1-4b, no Claude call).

    Upserts metadata, inserts snapshot, checks cache, runs Haiku screen.
    Returns a PreparedMarket if it should proceed to estimation, or None.
    """
    platform = market_data["platform"]
    platform_id = market_data["platform_id"]

    market_processing(market_data.get("question", "Unknown")[:80])

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
            outcome_label=market_data.get("outcome_label"),
        )

        # Step 2: Skip markets with no valid price (thin/fresh order book)
        price_yes = market_data.get("price_yes", 0.0)
        if price_yes <= 0 or price_yes >= 1.0:
            logger.info(
                "Scanner: skipping '%s' — no valid price (%.2f)",
                market_data["question"][:60],
                price_yes,
            )
            market_done("skipped")
            return None

        # Step 3: Insert price snapshot
        snapshot = insert_snapshot(
            market_id=market_row.id,
            price_yes=price_yes,
            price_no=market_data.get("price_no"),
            volume=market_data.get("volume"),
            liquidity=market_data.get("liquidity"),
        )

        # Step 4: Check if research is needed
        if not _needs_research(market_row.id, max_age_hours=settings.estimate_cache_hours):
            logger.debug(
                "Scanner: skipping '%s' — recent estimate exists",
                market_data["question"][:60],
            )
            market_done("skipped")
            return None

        # Step 5: Build blind input — NO PRICES, NO VOLUME
        feedback = get_calibration_feedback(
            category=market_data.get("category"),
        )
        blind_input = BlindMarketInput(
            question=market_data["question"],
            resolution_criteria=market_data.get("resolution_criteria"),
            close_date=market_data.get("close_date"),
            category=market_data.get("category"),
            sport_type=market_data.get("sport_type"),
            calibration_feedback=feedback,
        )

        # Step 5b: Haiku pre-screen — skip markets not worth researching
        should_research = await researcher.screen(blind_input)
        if not should_research:
            logger.info(
                "Scanner: Haiku screened out '%s'",
                market_data["question"][:60],
            )
            market_done("skipped")
            return None

        return PreparedMarket(
            market_id=market_row.id,
            market_data=market_data,
            snapshot_id=snapshot.id,
            snapshot_price_yes=snapshot.price_yes,
            blind_input=blind_input,
            volume=market_data.get("volume"),
            scan_id=scan_id,
        )

    except Exception:
        logger.exception(
            "Scanner: error preparing market '%s' on %s",
            market_data.get("question", "unknown")[:60],
            platform,
        )
        market_done(None)
        return None


async def _finalize_market(
    prepared: PreparedMarket,
    estimate_output,
    model_used: str,
    auto_trades: dict | None = None,
) -> str:
    """Store estimate, calculate EV, create recommendation, auto-trade.

    Returns ``"researched"`` or ``"recommended"``.
    """
    if auto_trades is None:
        auto_trades = {}

    market_data = prepared.market_data
    platform = market_data["platform"]

    # Step 6: Store estimate
    estimate_row = insert_estimate(
        market_id=prepared.market_id,
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
                scan_id=prepared.scan_id,
                market_id=prepared.market_id,
            )
        except Exception:
            logger.debug("Scanner: failed to log cost for %s", prepared.market_id)

    # Step 7: ONLY NOW use prices — compare AI estimate to market price
    ev_result = calculate_ev(
        ai_probability=estimate_output.probability,
        market_price=prepared.snapshot_price_yes,
        platform=platform,
    )

    if ev_result is not None and should_recommend(ev_result["ev"]):
        # Calculate Kelly fraction
        kelly = calculate_kelly(
            edge=ev_result["edge"],
            market_price=prepared.snapshot_price_yes,
            direction=ev_result["direction"],
            confidence=Confidence(estimate_output.confidence.value),
        )

        # Expire any old active recommendations for this market
        expire_recommendations(prepared.market_id)

        # Insert new recommendation
        rec = insert_recommendation(
            market_id=prepared.market_id,
            estimate_id=estimate_row.id,
            snapshot_id=prepared.snapshot_id,
            direction=ev_result["direction"],
            market_price=prepared.snapshot_price_yes,
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

        # Auto-trade if enabled and EV meets threshold
        db_config = get_config()
        auto_trade = db_config.get("auto_trade_enabled", False)
        auto_trade_min_ev = db_config.get("auto_trade_min_ev", 0.05)
        if auto_trade and ev_result["ev"] >= auto_trade_min_ev and platform == "kalshi":
            bankroll = db_config.get("bankroll", 1000)
            max_bet_frac = db_config.get("max_single_bet_fraction", 0.05)
            max_bet = bankroll * max_bet_frac
            bet_amount = min(kelly * bankroll, max_bet)
            if bet_amount >= 1.0:
                try:
                    from services.kalshi import KalshiClient

                    kalshi = KalshiClient()
                    if ev_result["direction"] == "yes":
                        price_cents = max(1, min(99, round(prepared.snapshot_price_yes * 100)))
                        price_per_contract = price_cents / 100.0
                    else:
                        price_cents = max(1, min(99, round(prepared.snapshot_price_yes * 100)))
                        price_per_contract = (100 - price_cents) / 100.0
                    count = max(1, int(bet_amount / price_per_contract))
                    actual_amount = round(count * price_per_contract, 2)

                    order = await kalshi.place_order(
                        ticker=market_data.get("platform_id", ""),
                        side=ev_result["direction"],
                        count=count,
                        yes_price=price_cents,
                    )
                    order_id = order.get("order", {}).get("order_id")
                    insert_trade(
                        market_id=prepared.market_id,
                        platform="kalshi",
                        direction=ev_result["direction"],
                        entry_price=price_per_contract,
                        amount=actual_amount,
                        shares=float(count),
                        recommendation_id=rec.id,
                        source="api_sync",
                        notes="Auto-trade from scanner",
                        platform_trade_id=f"order_{order_id}" if order_id else None,
                    )
                    # Track auto-trade for notification
                    auto_trades[rec.id] = {
                        "contracts": count,
                        "price_cents": price_cents,
                        "amount": actual_amount,
                    }
                    logger.info(
                        "Scanner: auto-trade placed for '%s' — %s %d contracts at %d¢ ($%.2f)",
                        market_data["question"][:60],
                        ev_result["direction"],
                        count,
                        price_cents,
                        actual_amount,
                    )
                except Exception:
                    logger.exception(
                        "Scanner: auto-trade failed for '%s'",
                        market_data["question"][:60],
                    )

        market_done("recommended")
        return "recommended"

    market_done("researched")
    return "researched"


async def _process_market(
    market_data: dict,
    researcher: Researcher,
    scan_id: str | None = None,
    use_premium: bool = False,
    auto_trades: dict | None = None,
) -> Optional[str]:
    """Process a single market through the full pipeline (sync mode).

    Thin wrapper: prepare → estimate → finalize.
    """
    if auto_trades is None:
        auto_trades = {}

    prepared = await _prepare_market(market_data, researcher, scan_id=scan_id)
    if prepared is None:
        return "skipped"

    try:
        # Step 5: Call researcher (volume used ONLY for model selection)
        async with _claude_semaphore:
            estimate_output = await researcher.estimate(
                blind_input=prepared.blind_input,
                volume=prepared.volume,
                use_premium=use_premium,
            )

        model_used = researcher._select_model(
            volume=prepared.volume,
            use_premium=use_premium,
        )

        return await _finalize_market(
            prepared, estimate_output, model_used, auto_trades=auto_trades,
        )

    except Exception:
        logger.exception(
            "Scanner: error processing market '%s' on %s",
            market_data.get("question", "unknown")[:60],
            market_data.get("platform", "unknown"),
        )
        market_done(None)
        return None


async def _execute_batch_pipeline(
    market_list: list[dict],
    researcher: Researcher,
    scan_id: str | None,
    use_premium: bool,
    auto_trades: dict,
) -> list[str]:
    """Run batch estimation pipeline: prepare all → batch estimate → finalize all.

    Falls back to sync mode if batch fails or returns no results.

    Returns:
        List of result strings ("researched", "recommended", "skipped").
    """
    # Phase 1: Prepare all markets concurrently
    prepare_tasks = [
        _prepare_market(m, researcher, scan_id=scan_id)
        for m in market_list
    ]
    prepare_results = await asyncio.gather(*prepare_tasks, return_exceptions=True)

    prepared_markets: list[PreparedMarket] = []
    for result in prepare_results:
        if isinstance(result, Exception):
            logger.error("Scanner: prepare exception: %s", result)
        elif result is not None:
            prepared_markets.append(result)

    if not prepared_markets:
        logger.info("Scanner: batch — no markets to estimate after preparation")
        return []

    logger.info(
        "Scanner: batch — %d markets prepared, submitting batch",
        len(prepared_markets),
    )

    # Phase 2: Batch estimation
    batch_items = [
        (p.market_id, p.blind_input) for p in prepared_markets
    ]
    volume_map = {
        p.market_id: p.volume
        for p in prepared_markets if p.volume is not None
    }

    update_batch_status(len(prepared_markets), 0)

    try:
        batch_estimates = await researcher.estimate_batch(
            items=batch_items,
            use_premium=use_premium,
            volume_map=volume_map,
        )
    except Exception:
        logger.exception(
            "Scanner: batch estimation failed, falling back to sync mode"
        )
        # Fallback: process remaining markets individually
        fallback_results = []
        for p in prepared_markets:
            try:
                async with _claude_semaphore:
                    est = await researcher.estimate(
                        blind_input=p.blind_input,
                        volume=p.volume,
                        use_premium=use_premium,
                    )
                model_used = researcher._select_model(
                    volume=p.volume, use_premium=use_premium,
                )
                r = await _finalize_market(p, est, model_used, auto_trades=auto_trades)
                fallback_results.append(r)
            except Exception:
                logger.exception("Scanner: sync fallback failed for %s", p.market_id)
        return fallback_results

    if not batch_estimates:
        logger.warning("Scanner: batch returned no results")
        return []

    # Phase 3: Finalize all with batch results
    model_used = researcher._select_model(use_premium=use_premium)
    finalize_results: list[str] = []

    for prepared in prepared_markets:
        estimate_output = batch_estimates.get(prepared.market_id)
        if estimate_output is None:
            logger.warning(
                "Scanner: batch missing result for %s, skipping",
                prepared.market_id,
            )
            market_done(None)
            continue

        try:
            result = await _finalize_market(
                prepared, estimate_output, model_used, auto_trades=auto_trades,
            )
            finalize_results.append(result)
        except Exception:
            logger.exception(
                "Scanner: finalize failed for %s",
                prepared.market_id,
            )

    update_batch_status(len(prepared_markets), len(finalize_results))

    logger.info(
        "Scanner: batch pipeline complete — %d/%d finalized",
        len(finalize_results), len(prepared_markets),
    )

    return finalize_results


async def execute_scan(
    platform: Optional[str] = None,
    use_batch: bool = False,
) -> ScanStatusResponse:
    """Execute a full market scan across one or all platforms.

    For each enabled platform:
      1. Fetch active markets from the platform API.
      2. Process each market through the blind estimation pipeline.

    Args:
        platform: If provided, scan only this platform.
                  Otherwise scan all enabled platforms.
        use_batch: If True, use Anthropic Batch API (50% cheaper, ~30min delay).

    Returns:
        ScanStatusResponse with summary statistics.
    """
    start_scan(platform=platform)

    started_at = datetime.now(timezone.utc)
    scan_id = str(uuid.uuid4())
    researcher = Researcher()

    # Determine which platforms to scan (Kalshi-only for now)
    if platform:
        platforms = [platform]
    else:
        platforms = [Platform.kalshi.value]

    markets_found = 0
    markets_researched = 0
    recommendations_created = 0
    markets_date_filtered = 0
    auto_trades: dict[str, dict] = {}  # rec_id -> {contracts, price_cents, amount}

    # Read runtime config from database (UI-editable settings)
    db_config = get_config()
    run_min_volume = db_config.get("min_volume", settings.min_volume)
    run_markets_per_platform = db_config.get(
        "markets_per_platform", settings.markets_per_platform
    )

    # Close date window: skip markets closing too soon or too far out
    run_max_close_hours = db_config.get("max_close_hours", 24)
    use_premium = db_config.get("use_premium_model", False)
    now = datetime.now(timezone.utc)
    min_close = now + timedelta(hours=2)
    max_close = now + timedelta(hours=run_max_close_hours)

    try:
        for plat in platforms:
            try:
                client = _get_platform_client(plat)

                logger.info("Scanner: fetching markets from %s", plat)
                # Pass close-date window to Kalshi API for server-side
                # filtering (avoids paginating through thousands of
                # irrelevant far-future markets).
                fetch_kwargs: dict = {
                    "limit": run_markets_per_platform,
                    "min_volume": run_min_volume,
                }
                if plat == "kalshi":
                    fetch_kwargs["min_close_ts"] = int(min_close.timestamp())
                    fetch_kwargs["max_close_ts"] = int(max_close.timestamp())
                market_list = await client.fetch_markets(**fetch_kwargs)

                # Filter by close date: keep only markets closing 2h–24h from now
                before_count = len(market_list)
                filtered_list = []
                for m in market_list:
                    close_str = m.get("close_date")
                    if close_str:
                        try:
                            close_dt = datetime.fromisoformat(
                                close_str.replace("Z", "+00:00")
                            )
                            if close_dt < min_close or close_dt > max_close:
                                continue
                        except (ValueError, TypeError):
                            pass  # keep if unparseable
                    filtered_list.append(m)

                date_skipped = before_count - len(filtered_list)
                markets_date_filtered += date_skipped
                market_list = filtered_list
                markets_found += len(market_list)

                set_markets_found(before_count, len(market_list))

                logger.info(
                    "Scanner: %d markets from %s (%d skipped by close-date filter)",
                    len(market_list),
                    plat,
                    date_skipped,
                )

                if use_batch:
                    # ── Batch mode: prepare → batch estimate → finalize ──
                    batch_results = await _execute_batch_pipeline(
                        market_list, researcher, scan_id,
                        use_premium, auto_trades,
                    )
                    for result in batch_results:
                        if result == "researched":
                            markets_researched += 1
                        elif result == "recommended":
                            markets_researched += 1
                            recommendations_created += 1
                else:
                    # ── Sync mode: process each market individually ──
                    tasks = [
                        _process_market(
                            m, researcher, scan_id=scan_id,
                            use_premium=use_premium,
                            auto_trades=auto_trades,
                        )
                        for m in market_list
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
        complete_scan()

        duration_seconds = (completed_at - started_at).total_seconds()
        logger.info(
            "Scanner: scan complete — found=%d researched=%d recommended=%d "
            "duration=%.1fs",
            markets_found,
            markets_researched,
            recommendations_created,
            duration_seconds,
        )

        # Save scan summary for dashboard card
        save_scan_summary({
            "markets_found": markets_found,
            "markets_researched": markets_researched,
            "recommendations_created": recommendations_created,
            "duration_seconds": round(duration_seconds, 1),
            "completed_at": completed_at.isoformat(),
        })

        # Send notifications for newly created recommendations
        if recommendations_created > 0:
            try:
                active_recs = get_active_recommendations()
                # Filter to recommendations created during this scan
                new_recs = [
                    r for r in active_recs
                    if r.created_at >= started_at
                ]
                if new_recs:
                    # Build notification payloads with market details
                    notification_recs = []
                    for r in new_recs:
                        market = get_market(r.market_id)
                        if market:
                            rec_data = {
                                "question": market.question,
                                "direction": r.direction,
                                "edge": r.edge,
                                "ev": r.ev,
                                "ai_probability": r.ai_probability,
                                "market_price": r.market_price,
                                "kelly_fraction": r.kelly_fraction,
                                "outcome_label": market.outcome_label,
                                "platform_id": market.platform_id,
                            }
                            trade_info = auto_trades.get(r.id)
                            if trade_info:
                                rec_data["auto_trade"] = trade_info
                            notification_recs.append(rec_data)
                    if notification_recs:
                        await send_scan_notifications(
                            recommendations=notification_recs,
                            scan_summary={
                                "markets_found": markets_found,
                                "markets_researched": markets_researched,
                                "recommendations_created": recommendations_created,
                                "duration_seconds": duration_seconds,
                            },
                        )
            except Exception:
                logger.exception("Scanner: notification send failed (non-fatal)")

        # Auto-trade sweep: place trades for active recs that haven't been traded
        sweep_trades: list[dict] = []
        if db_config.get("auto_trade_enabled", False):
            try:
                sweep_trades = await _sweep_untraded_recs(db_config)
            except Exception:
                logger.exception("Scanner: auto-trade sweep failed (non-fatal)")

        # Send sweep notifications
        if sweep_trades:
            try:
                from services.notifier import send_sweep_notifications

                await send_sweep_notifications(sweep_trades)
            except Exception:
                logger.exception("Scanner: sweep notification failed (non-fatal)")

        return ScanStatusResponse(
            status="completed",
            platform=platform,
            markets_found=markets_found,
            markets_researched=markets_researched,
            recommendations_created=recommendations_created,
            started_at=started_at,
            completed_at=completed_at,
        )

    except Exception as exc:
        fail_scan(str(exc))
        logger.exception("Scanner: scan failed unexpectedly")
        raise


async def _sweep_untraded_recs(db_config: dict) -> list[dict]:
    """Place trades for active recommendations that haven't been traded yet.

    Called after each scan when auto_trade_enabled is True.  Re-verifies EV
    using the latest snapshot price before placing each order.

    Returns:
        List of dicts describing placed trades (for notifications).
    """
    untraded = get_untraded_active_recommendations()
    if not untraded:
        return []

    auto_trade_min_ev = db_config.get("auto_trade_min_ev", 0.05)
    bankroll = db_config.get("bankroll", 1000)
    max_bet_frac = db_config.get("max_single_bet_fraction", 0.05)
    max_bet = bankroll * max_bet_frac

    kalshi = KalshiClient()
    sweep_results: list[dict] = []

    for rec in untraded:
        try:
            market = get_market(rec.market_id)
            if not market or market.platform != "kalshi" or market.status != "active":
                continue

            # Use latest snapshot price to re-verify EV
            snapshot = get_latest_snapshot(rec.market_id)
            if not snapshot:
                continue

            ev_result = calculate_ev(
                ai_probability=rec.ai_probability,
                market_price=snapshot.price_yes,
                platform="kalshi",
            )
            if ev_result is None or ev_result["ev"] < auto_trade_min_ev:
                logger.info(
                    "Sweep: skipping '%s' — EV %.1f%% below threshold",
                    market.question[:60],
                    (ev_result["ev"] * 100) if ev_result else 0,
                )
                continue

            kelly = calculate_kelly(
                edge=ev_result["edge"],
                market_price=snapshot.price_yes,
                direction=ev_result["direction"],
                confidence=Confidence("medium"),  # conservative default
            )

            bet_amount = min(kelly * bankroll, max_bet)
            if bet_amount < 1.0:
                continue

            if ev_result["direction"] == "yes":
                price_cents = max(1, min(99, round(snapshot.price_yes * 100)))
                price_per_contract = price_cents / 100.0
            else:
                price_cents = max(1, min(99, round(snapshot.price_yes * 100)))
                price_per_contract = (100 - price_cents) / 100.0

            count = max(1, int(bet_amount / price_per_contract))
            actual_amount = round(count * price_per_contract, 2)

            order = await kalshi.place_order(
                ticker=market.platform_id,
                side=ev_result["direction"],
                count=count,
                yes_price=price_cents,
            )
            order_id = order.get("order", {}).get("order_id")
            insert_trade(
                market_id=market.id,
                platform="kalshi",
                direction=ev_result["direction"],
                entry_price=price_per_contract,
                amount=actual_amount,
                shares=float(count),
                recommendation_id=rec.id,
                source="api_sync",
                notes="Auto-trade sweep (existing rec)",
                platform_trade_id=f"order_{order_id}" if order_id else None,
            )
            sweep_results.append({
                "question": market.question,
                "direction": ev_result["direction"],
                "edge": ev_result["edge"],
                "ev": ev_result["ev"],
                "ai_probability": rec.ai_probability,
                "market_price": snapshot.price_yes,
                "kelly_fraction": kelly,
                "outcome_label": market.outcome_label,
                "platform_id": market.platform_id,
                "auto_trade": {
                    "contracts": count,
                    "price_cents": price_cents,
                    "amount": actual_amount,
                },
            })
            logger.info(
                "Sweep: trade placed for '%s' — %s %d contracts at %d¢ ($%.2f)",
                market.question[:60],
                ev_result["direction"],
                count,
                price_cents,
                actual_amount,
            )

        except Exception:
            logger.exception(
                "Sweep: failed to trade rec %s for market %s",
                rec.id,
                rec.market_id,
            )

    logger.info("Sweep: placed %d trades for %d untraded recs", len(sweep_results), len(untraded))
    return sweep_results


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

    Called when a market resolution is detected via platform APIs.
    Closes all open trades, calculates P&L, computes simulated P&L
    from the recommendation, and records the AI's calibration data
    in the performance_log table.

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

        # Look up recommendation for simulated P&L + linking
        recommendation = get_recommendation_for_market(market_id)
        simulated_pnl = None
        if recommendation:
            cfg = get_config()
            bankroll = float(cfg.get("bankroll", settings.bankroll))
            simulated_pnl = calculate_pnl(
                market_price=recommendation.market_price,
                direction=recommendation.direction,
                outcome=outcome,
                kelly_fraction_used=recommendation.kelly_fraction,
                bankroll=bankroll,
            )

        insert_performance(
            market_id=market_id,
            ai_probability=estimate.probability,
            market_price=snapshot.price_yes,
            actual_outcome=outcome,
            brier_score=brier,
            recommendation_id=recommendation.id if recommendation else None,
            pnl=total_pnl if closed_trades else None,
            simulated_pnl=simulated_pnl,
        )

    logger.info(
        "Scanner: resolved market %s — outcome=%s, closed %d trades, simulated_pnl=%s",
        market_id,
        outcome,
        len(closed_trades),
        simulated_pnl if estimate and snapshot else "n/a",
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
    platforms_to_check = [Platform.kalshi.value]

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
