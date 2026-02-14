"""Trade tracking endpoints.

Provides CRUD for user trades, portfolio statistics, and
AI vs actual performance comparison.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from models.schemas import (
    MarketRow,
    TradeRow,
    TradeCreateRequest,
    TradeUpdateRequest,
    TradeListResponse,
    TradeWithMarket,
    PortfolioStatsResponse,
    AIvsActualResponse,
    TradeSyncStatusResponse,
    ExecuteTradeRequest,
)
from models.database import (
    insert_trade,
    get_trade,
    list_trades,
    count_trades,
    update_trade,
    delete_trade,
    get_open_trades,
    get_closed_trades,
    get_market,
    get_latest_snapshot,
    get_recommendation,
    get_active_recommendations,
    get_recommendation_history,
    get_performance_aggregate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trades", tags=["trades"])


def _build_markets_dict(trades: list[TradeRow]) -> dict[str, MarketRow]:
    """Look up the market for each trade."""
    markets: dict[str, MarketRow] = {}
    for trade in trades:
        if trade.market_id not in markets:
            market = get_market(trade.market_id)
            if market is not None:
                markets[trade.market_id] = market
    return markets


@router.post("/sync")
async def trigger_trade_sync(background_tasks: BackgroundTasks) -> dict:
    """Trigger trade sync from connected platform accounts.

    Runs in the background. Check status via GET /trades/sync/status.
    """
    async def _run_sync() -> None:
        try:
            from services.trade_syncer import sync_all_trades

            result = await sync_all_trades()
            logger.info("Trade sync triggered manually — %s", result)
        except Exception:
            logger.exception("Manual trade sync failed")

    background_tasks.add_task(_run_sync)
    return {"status": "running"}


@router.get("/sync/status", response_model=TradeSyncStatusResponse)
async def get_trade_sync_status() -> TradeSyncStatusResponse:
    """Get the most recent trade sync status for each platform."""
    from services.trade_syncer import get_last_sync_status

    status = get_last_sync_status()
    return TradeSyncStatusResponse(platforms=status)


@router.post("/execute")
async def execute_trade(request: ExecuteTradeRequest) -> dict:
    """Place a bet on Kalshi from a recommendation.

    Looks up the recommendation + market, calculates contracts + price,
    places an order on Kalshi, and logs the trade in the DB.
    """
    rec = get_recommendation(request.recommendation_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    market = get_market(rec.market_id)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")

    if market.platform != "kalshi":
        raise HTTPException(
            status_code=400, detail="Only Kalshi markets support direct execution"
        )

    snapshot = get_latest_snapshot(rec.market_id)
    if snapshot is None:
        raise HTTPException(status_code=400, detail="No price snapshot available")

    # Calculate order parameters
    # Price in cents (1-99). Use the recommendation's market_price.
    if rec.direction == "yes":
        price_cents = max(1, min(99, round(snapshot.price_yes * 100)))
        price_per_contract = price_cents / 100.0
    else:
        price_cents = max(1, min(99, round(snapshot.price_yes * 100)))
        price_per_contract = (100 - price_cents) / 100.0

    # Number of contracts = dollar amount / price per contract
    count = max(1, int(request.amount / price_per_contract))

    # Place the order on Kalshi
    from services.kalshi import KalshiClient

    client = KalshiClient()
    try:
        order_result = await client.place_order(
            ticker=market.platform_id,
            side=rec.direction,
            count=count,
            yes_price=price_cents,
        )
    except Exception as exc:
        logger.exception("Failed to place Kalshi order for %s", market.platform_id)
        raise HTTPException(
            status_code=502,
            detail=f"Kalshi order failed: {exc}",
        )

    # Log the trade in the DB
    order_info = order_result.get("order", {})
    order_id = order_info.get("order_id")
    actual_amount = round(count * price_per_contract, 2)
    trade = insert_trade(
        market_id=rec.market_id,
        platform="kalshi",
        direction=rec.direction,
        entry_price=price_per_contract,
        amount=actual_amount,
        shares=float(count),
        recommendation_id=rec.id,
        source="api_sync",
        notes="Auto-executed via Kalshi API",
        platform_trade_id=f"order_{order_id}" if order_id else None,
    )
    logger.info(
        "Trade executed: %s — %s %d contracts at %d¢ ($%.2f) — order_id=%s",
        market.platform_id,
        rec.direction,
        count,
        price_cents,
        actual_amount,
        order_info.get("order_id", "unknown"),
    )

    return {
        "status": "executed",
        "trade_id": trade.id,
        "order": order_info,
        "contracts": count,
        "price_cents": price_cents,
        "total_cost": actual_amount,
        "direction": rec.direction,
        "market": market.question,
    }


@router.post("", response_model=TradeRow, status_code=201)
async def create_trade(request: TradeCreateRequest) -> TradeRow:
    """Log a new trade.

    User places a trade on a prediction market platform and records it here.
    Shares are auto-calculated as amount / entry_price if not provided.
    """
    market = get_market(request.market_id)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")

    shares = request.shares
    if shares is None and request.entry_price > 0:
        if request.direction.value == "yes":
            shares = round(request.amount / request.entry_price, 4)
        else:
            no_price = 1.0 - request.entry_price
            shares = round(request.amount / no_price, 4) if no_price > 0 else 0

    trade = insert_trade(
        market_id=request.market_id,
        platform=request.platform.value,
        direction=request.direction.value,
        entry_price=request.entry_price,
        amount=request.amount,
        shares=shares,
        fees_paid=request.fees_paid,
        notes=request.notes,
        recommendation_id=request.recommendation_id,
    )

    logger.info(
        "Trade created: %s on %s — $%.2f %s at %.4f",
        trade.id,
        request.platform.value,
        request.amount,
        request.direction.value,
        request.entry_price,
    )
    return trade


@router.get("", response_model=TradeListResponse)
async def list_all_trades(
    status: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> TradeListResponse:
    """List all trades with optional filters."""
    trades = list_trades(
        status=status, platform=platform, limit=limit, offset=offset
    )
    total = count_trades(status=status, platform=platform)
    markets = _build_markets_dict(trades)
    return TradeListResponse(trades=trades, markets=markets, total=total)


@router.get("/open", response_model=TradeListResponse)
async def list_open_trades() -> TradeListResponse:
    """Get all open positions."""
    trades = get_open_trades()
    markets = _build_markets_dict(trades)
    return TradeListResponse(trades=trades, markets=markets, total=len(trades))


@router.get("/portfolio", response_model=PortfolioStatsResponse)
async def get_portfolio_stats() -> PortfolioStatsResponse:
    """Get portfolio summary statistics.

    Calculates open positions, unrealized P&L (using current market prices),
    realized P&L, win rate, and average return.
    """
    open_trades = get_open_trades()
    closed_trades = get_closed_trades(limit=1000)

    total_invested = sum(t.amount for t in open_trades)
    unrealized_pnl = 0.0
    for trade in open_trades:
        snapshot = get_latest_snapshot(trade.market_id)
        if snapshot:
            current_price = snapshot.price_yes
            if trade.direction == "yes":
                current_value = (trade.shares or 0) * current_price
                unrealized_pnl += current_value - trade.amount
            else:
                current_no_price = 1.0 - current_price
                current_value = (trade.shares or 0) * current_no_price
                unrealized_pnl += current_value - trade.amount

    realized_pnl = sum(t.pnl or 0 for t in closed_trades)
    wins = sum(1 for t in closed_trades if (t.pnl or 0) > 0)
    win_rate = wins / len(closed_trades) if closed_trades else 0.0
    avg_return = (
        sum((t.pnl or 0) / t.amount for t in closed_trades if t.amount > 0)
        / len(closed_trades)
        if closed_trades
        else 0.0
    )

    return PortfolioStatsResponse(
        open_positions=len(open_trades),
        total_invested=round(total_invested, 2),
        unrealized_pnl=round(unrealized_pnl, 2),
        realized_pnl=round(realized_pnl, 2),
        total_pnl=round(unrealized_pnl + realized_pnl, 2),
        total_trades=len(open_trades) + len(closed_trades),
        win_rate=round(win_rate, 4),
        avg_return=round(avg_return, 4),
    )


@router.get("/comparison", response_model=AIvsActualResponse)
async def get_ai_vs_actual() -> AIvsActualResponse:
    """Compare AI recommendation performance vs actual trade performance."""
    all_recs = get_recommendation_history(limit=1000, offset=0)
    closed_trades = get_closed_trades(limit=1000)

    traded_rec_ids = {
        t.recommendation_id for t in closed_trades if t.recommendation_id
    }
    recs_traded = sum(1 for r in all_recs if r.id in traded_rec_ids)

    perf_data = get_performance_aggregate()
    ai_hit_rate = perf_data.get("hit_rate", 0.0)
    ai_brier = perf_data.get("avg_brier_score", 0.0)
    ai_avg_edge = perf_data.get("avg_edge", 0.0)

    wins = sum(1 for t in closed_trades if (t.pnl or 0) > 0)
    actual_hit_rate = wins / len(closed_trades) if closed_trades else 0.0
    actual_avg_return = (
        sum((t.pnl or 0) / t.amount for t in closed_trades if t.amount > 0)
        / len(closed_trades)
        if closed_trades
        else 0.0
    )

    comparison_rows = []
    for trade in closed_trades:
        market = get_market(trade.market_id)
        rec_edge = None
        rec_direction = None
        if trade.recommendation_id:
            for r in all_recs:
                if r.id == trade.recommendation_id:
                    rec_edge = r.edge
                    rec_direction = r.direction
                    break

        comparison_rows.append(
            {
                "market_id": trade.market_id,
                "question": market.question if market else "Unknown",
                "trade_direction": trade.direction,
                "trade_pnl": trade.pnl,
                "trade_return": (
                    round((trade.pnl or 0) / trade.amount, 4)
                    if trade.amount > 0
                    else 0
                ),
                "ai_direction": rec_direction,
                "ai_edge": rec_edge,
                "followed_ai": (
                    trade.direction == rec_direction if rec_direction else None
                ),
            }
        )

    return AIvsActualResponse(
        total_ai_recommendations=len(all_recs),
        recommendations_traded=recs_traded,
        recommendations_not_traded=len(all_recs) - recs_traded,
        ai_hit_rate=round(ai_hit_rate, 4),
        actual_hit_rate=round(actual_hit_rate, 4),
        ai_avg_edge=round(ai_avg_edge, 4),
        actual_avg_return=round(actual_avg_return, 4),
        ai_brier_score=round(ai_brier, 4),
        comparison_rows=comparison_rows,
    )


@router.get("/{trade_id}", response_model=TradeWithMarket)
async def get_trade_detail(trade_id: str) -> TradeWithMarket:
    """Get a single trade with its associated market."""
    trade = get_trade(trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    market = get_market(trade.market_id)
    if market is None:
        raise HTTPException(
            status_code=404, detail="Associated market not found"
        )
    return TradeWithMarket(trade=trade, market=market)


@router.patch("/{trade_id}", response_model=TradeRow)
async def update_trade_endpoint(
    trade_id: str, request: TradeUpdateRequest
) -> TradeRow:
    """Update a trade (close, cancel, update notes).

    When closing with an exit_price, P&L is auto-calculated if not provided.
    """
    existing = get_trade(trade_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Trade not found")

    updates = request.model_dump(exclude_none=True)

    if updates.get("status") == "closed":
        updates["closed_at"] = datetime.now(timezone.utc).isoformat()

        if "exit_price" in updates and "pnl" not in updates:
            exit_price = updates["exit_price"]
            if existing.direction == "yes":
                if exit_price >= 0.99:
                    pnl = (
                        existing.amount
                        * (1.0 - existing.entry_price)
                        / existing.entry_price
                    )
                else:
                    pnl = -existing.amount
            else:
                if exit_price <= 0.01:
                    no_price = 1.0 - existing.entry_price
                    pnl = (
                        existing.amount * existing.entry_price / no_price
                        if no_price > 0
                        else 0
                    )
                else:
                    pnl = -existing.amount
            pnl -= existing.fees_paid
            updates["pnl"] = round(pnl, 4)

    if updates.get("status") == "cancelled":
        updates["closed_at"] = datetime.now(timezone.utc).isoformat()
        updates["pnl"] = 0.0

    updated = update_trade(trade_id, updates)
    if updated is None:
        raise HTTPException(status_code=500, detail="Failed to update trade")

    return updated


@router.delete("/{trade_id}")
async def delete_trade_endpoint(trade_id: str) -> dict:
    """Delete a trade (only if open or cancelled)."""
    existing = get_trade(trade_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    if existing.status == "closed":
        raise HTTPException(
            status_code=400, detail="Cannot delete a closed trade"
        )

    delete_trade(trade_id)
    return {"status": "deleted"}
