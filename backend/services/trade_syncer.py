"""Trade sync service — fetches trades from platform APIs and syncs to local database.

Supports:
  - Polymarket: wallet-address-based position fetching (no auth)
  - Kalshi: RSA-PSS authenticated fills

Deduplicates on (platform, platform_trade_id) to avoid double-counting.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from config import settings
from models.database import (
    get_supabase,
    insert_trade,
    update_trade,
)
from services.polymarket import PolymarketClient
from services.kalshi import KalshiClient

logger = logging.getLogger(__name__)


# ── Helper Functions ──


def _get_existing_synced_trade_ids(platform: str) -> set[str]:
    """Get all platform_trade_ids already in the database for a platform.

    Used for deduplication before inserting new synced trades.
    """
    db = get_supabase()
    result = (
        db.table("trades")
        .select("platform_trade_id")
        .eq("platform", platform)
        .eq("source", "api_sync")
        .not_.is_("platform_trade_id", "null")
        .execute()
    )
    return {row["platform_trade_id"] for row in result.data}


def _get_market_id_by_platform(
    platform: str, platform_id: str
) -> Optional[str]:
    """Look up internal market_id by (platform, platform_id).

    Returns None if the market isn't tracked in our database.
    """
    db = get_supabase()
    result = (
        db.table("markets")
        .select("id")
        .eq("platform", platform)
        .eq("platform_id", platform_id)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["id"]
    return None


def _get_recommendation_for_market(market_id: str) -> Optional[str]:
    """Find the latest recommendation for a market, if any.

    Used to link synced trades back to AI recommendations.
    """
    db = get_supabase()
    result = (
        db.table("recommendations")
        .select("id")
        .eq("market_id", market_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["id"]
    return None


def _insert_sync_log(platform: str) -> str:
    """Create a trade_sync_log entry and return its ID."""
    db = get_supabase()
    result = (
        db.table("trade_sync_log")
        .insert({"platform": platform, "status": "running"})
        .execute()
    )
    return result.data[0]["id"]


def _update_sync_log(
    log_id: str,
    status: str,
    trades_found: int = 0,
    trades_created: int = 0,
    trades_updated: int = 0,
    trades_skipped: int = 0,
    error_message: Optional[str] = None,
) -> None:
    """Update a trade_sync_log entry with results."""
    db = get_supabase()
    db.table("trade_sync_log").update(
        {
            "status": status,
            "trades_found": trades_found,
            "trades_created": trades_created,
            "trades_updated": trades_updated,
            "trades_skipped": trades_skipped,
            "error_message": error_message,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", log_id).execute()


# ── Polymarket Sync ──


async def sync_polymarket_trades() -> dict:
    """Sync positions from Polymarket Data API.

    Flow:
      1. Fetch all positions for the configured wallet address.
      2. For each position, look up the market by conditionId.
      3. If market exists and trade not already synced, insert new trade.
      4. If position size changed, update existing trade.

    Returns:
        Summary dict with counts.
    """
    wallet = settings.polymarket_wallet_address
    if not wallet:
        logger.info(
            "Polymarket trade sync: no wallet address configured, skipping"
        )
        return {"platform": "polymarket", "status": "skipped"}

    log_id = _insert_sync_log("polymarket")

    try:
        client = PolymarketClient()
        positions = await client.fetch_positions(wallet)

        existing_ids = _get_existing_synced_trade_ids("polymarket")

        created = 0
        updated = 0
        skipped = 0

        for pos in positions:
            condition_id = pos.get("conditionId", "")
            outcome_index = pos.get("outcomeIndex", "")
            size = float(pos.get("size", 0))
            avg_price = float(pos.get("avgPrice", 0))

            if size == 0:
                skipped += 1
                continue

            # Unique ID: conditionId + outcomeIndex
            platform_trade_id = f"{condition_id}_{outcome_index}"

            if platform_trade_id in existing_ids:
                # Check if position size changed
                db = get_supabase()
                existing_result = (
                    db.table("trades")
                    .select("id, shares")
                    .eq("platform", "polymarket")
                    .eq("platform_trade_id", platform_trade_id)
                    .limit(1)
                    .execute()
                )
                if existing_result.data:
                    existing = existing_result.data[0]
                    existing_shares = float(existing.get("shares") or 0)

                    if abs(size - existing_shares) > 0.01:
                        amount = size * avg_price
                        update_trade(
                            existing["id"],
                            {
                                "shares": round(size, 4),
                                "amount": round(amount, 2),
                                "entry_price": round(avg_price, 4),
                            },
                        )
                        updated += 1
                    else:
                        skipped += 1
                else:
                    skipped += 1
                continue

            # Look up market in our database
            market_id = _get_market_id_by_platform(
                "polymarket", condition_id
            )
            if market_id is None:
                logger.debug(
                    "Polymarket sync: skipping untracked market %s",
                    condition_id,
                )
                skipped += 1
                continue

            # outcomeIndex: 1 = YES, 0 = NO
            direction = "yes" if str(outcome_index) == "1" else "no"
            amount = size * avg_price
            rec_id = _get_recommendation_for_market(market_id)
            title = pos.get("title", "")[:100]

            insert_trade(
                market_id=market_id,
                platform="polymarket",
                direction=direction,
                entry_price=round(avg_price, 4),
                amount=round(amount, 2),
                shares=round(size, 4),
                fees_paid=0.0,
                notes=f"[Auto-synced] {title}",
                recommendation_id=rec_id,
                source="api_sync",
                platform_trade_id=platform_trade_id,
            )
            created += 1

        _update_sync_log(
            log_id,
            "completed",
            trades_found=len(positions),
            trades_created=created,
            trades_updated=updated,
            trades_skipped=skipped,
        )

        logger.info(
            "Polymarket sync: found=%d created=%d updated=%d skipped=%d",
            len(positions),
            created,
            updated,
            skipped,
        )

        return {
            "platform": "polymarket",
            "status": "completed",
            "trades_found": len(positions),
            "trades_created": created,
            "trades_updated": updated,
            "trades_skipped": skipped,
        }

    except Exception as exc:
        logger.exception("Polymarket trade sync failed")
        _update_sync_log(log_id, "failed", error_message=str(exc))
        return {
            "platform": "polymarket",
            "status": "failed",
            "error": str(exc),
        }


# ── Kalshi Order Reconciliation ──


async def _reconcile_kalshi_orders(client: KalshiClient) -> dict:
    """Check open trades against Kalshi order status.

    For each trade in our DB with status='open' and platform_trade_id
    starting with 'order_', check if the order was cancelled on Kalshi.
    If cancelled → mark trade as cancelled with pnl=0.

    Returns:
        Summary dict with counts.
    """
    db = get_supabase()

    # 1. Find all open Kalshi trades that have an order-based platform_trade_id
    result = (
        db.table("trades")
        .select("id, platform_trade_id")
        .eq("platform", "kalshi")
        .eq("status", "open")
        .like("platform_trade_id", "order_%")
        .execute()
    )
    open_order_trades = result.data or []

    if not open_order_trades:
        logger.debug("Order reconciliation: no open order-based trades to check")
        return {"checked": 0, "cancelled": 0}

    # 2. Fetch cancelled orders from Kalshi
    cancelled_orders = await client.fetch_orders(status="canceled")
    cancelled_ids = {
        f"order_{o.get('order_id', '')}" for o in cancelled_orders
    }

    # 3. Mark matching trades as cancelled
    cancelled_count = 0
    for trade in open_order_trades:
        ptid = trade.get("platform_trade_id", "")
        if ptid in cancelled_ids:
            update_trade(
                trade["id"],
                {
                    "status": "cancelled",
                    "pnl": 0.0,
                    "closed_at": datetime.now(timezone.utc).isoformat(),
                    "notes": "[Auto-cancelled] Order cancelled on Kalshi",
                },
            )
            cancelled_count += 1
            logger.info(
                "Order reconciliation: cancelled trade %s (%s)",
                trade["id"],
                ptid,
            )

    logger.info(
        "Order reconciliation: checked=%d cancelled=%d",
        len(open_order_trades),
        cancelled_count,
    )
    return {"checked": len(open_order_trades), "cancelled": cancelled_count}


# ── Kalshi Sync ──


async def sync_kalshi_trades() -> dict:
    """Sync fills from Kalshi portfolio API.

    Flow:
      1. Fetch fills (trade history) from /portfolio/fills.
      2. For each fill, look up market by ticker.
      3. Deduplicate by fill_id as platform_trade_id.
      4. Insert new trades with source='api_sync'.

    Returns:
        Summary dict with counts.
    """
    client = KalshiClient()
    if not client.is_configured():
        logger.info("Kalshi trade sync: not configured, skipping")
        return {"platform": "kalshi", "status": "skipped"}

    log_id = _insert_sync_log("kalshi")

    try:
        fills = await client.fetch_fills(limit=500)
        existing_ids = _get_existing_synced_trade_ids("kalshi")

        created = 0
        updated = 0
        skipped = 0

        for fill in fills:
            fill_id = fill.get("fill_id", "")
            if not fill_id:
                skipped += 1
                continue

            platform_trade_id = f"fill_{fill_id}"

            if platform_trade_id in existing_ids:
                skipped += 1
                continue

            ticker = fill.get("ticker", "")
            market_id = _get_market_id_by_platform("kalshi", ticker)
            if market_id is None:
                logger.debug(
                    "Kalshi sync: skipping untracked market %s", ticker
                )
                skipped += 1
                continue

            # Parse fill fields (prices are in cents)
            side = fill.get("side", "").lower()
            action = fill.get("action", "").lower()
            count = int(fill.get("count", 0))
            yes_price = float(fill.get("yes_price", 50)) / 100
            no_price = float(fill.get("no_price", 50)) / 100
            fee_cost = float(fill.get("fee_cost", 0)) / 100

            # Determine direction and entry price
            direction = side if side in ("yes", "no") else "yes"
            entry_price = yes_price if direction == "yes" else no_price

            # Kalshi contracts are $1 each
            amount = count * entry_price
            shares = float(count)

            # Check for matching order-based trade (prevents duplicates)
            from models.database import find_order_trade_for_fill

            existing_order = find_order_trade_for_fill(
                market_id=market_id,
                direction=direction,
            )

            if existing_order:
                update_trade(
                    existing_order["id"],
                    {
                        "platform_trade_id": platform_trade_id,
                        "entry_price": round(entry_price, 4),
                        "amount": round(amount, 2),
                        "shares": round(shares, 4),
                        "fees_paid": round(fee_cost, 4),
                    },
                )
                existing_ids.add(platform_trade_id)
                updated += 1
                logger.info(
                    "Kalshi sync: matched fill %s to order trade %s",
                    fill_id,
                    existing_order["id"],
                )
                continue

            rec_id = _get_recommendation_for_market(market_id)

            insert_trade(
                market_id=market_id,
                platform="kalshi",
                direction=direction,
                entry_price=round(entry_price, 4),
                amount=round(amount, 2),
                shares=round(shares, 4),
                fees_paid=round(fee_cost, 4),
                notes=f"[Auto-synced] {action} {count}x {ticker}",
                recommendation_id=rec_id,
                source="api_sync",
                platform_trade_id=platform_trade_id,
            )
            created += 1

        # Reconcile open orders (detect cancellations)
        reconcile_result = await _reconcile_kalshi_orders(client)
        orders_cancelled = reconcile_result.get("cancelled", 0)

        _update_sync_log(
            log_id,
            "completed",
            trades_found=len(fills),
            trades_created=created,
            trades_updated=updated + orders_cancelled,
            trades_skipped=skipped,
        )

        logger.info(
            "Kalshi sync: found=%d created=%d matched=%d cancelled=%d skipped=%d",
            len(fills),
            created,
            updated,
            orders_cancelled,
            skipped,
        )

        return {
            "platform": "kalshi",
            "status": "completed",
            "trades_found": len(fills),
            "trades_created": created,
            "fills_matched_to_orders": updated,
            "orders_cancelled": orders_cancelled,
            "trades_skipped": skipped,
        }

    except Exception as exc:
        logger.exception("Kalshi trade sync failed")
        _update_sync_log(log_id, "failed", error_message=str(exc))
        return {
            "platform": "kalshi",
            "status": "failed",
            "error": str(exc),
        }


# ── Orchestrator ──


async def sync_all_trades() -> dict:
    """Sync trades from Kalshi (Kalshi-only mode).

    Returns:
        Summary dict with per-platform results.
    """
    results = {}

    kalshi = KalshiClient()
    if kalshi.is_configured():
        results["kalshi"] = await sync_kalshi_trades()

    logger.info("Trade sync complete: %s", results)
    return results


def get_last_sync_status() -> dict:
    """Get the most recent sync log entry for Kalshi."""
    db = get_supabase()

    status = {}
    result = (
        db.table("trade_sync_log")
        .select("*")
        .eq("platform", "kalshi")
        .order("started_at", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        status["kalshi"] = result.data[0]

    return status
