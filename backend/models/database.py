import logging
from datetime import datetime
from typing import Optional

from supabase import create_client, Client

from config import settings
from models.schemas import (
    MarketRow,
    SnapshotRow,
    AIEstimateRow,
    RecommendationRow,
    PerformanceRow,
    CalibrationBucket,
    TradeRow,
    CostLogRow,
)

logger = logging.getLogger(__name__)

_supabase_client: Optional[Client] = None


def get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(
            settings.supabase_url, settings.supabase_service_key
        )
    return _supabase_client


# ── Markets ──


def upsert_market(
    platform: str,
    platform_id: str,
    question: str,
    description: Optional[str] = None,
    resolution_criteria: Optional[str] = None,
    category: Optional[str] = None,
    close_date: Optional[str] = None,
) -> MarketRow:
    db = get_supabase()
    data = {
        "platform": platform,
        "platform_id": platform_id,
        "question": question,
        "description": description,
        "resolution_criteria": resolution_criteria,
        "category": category,
        "close_date": close_date,
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        result = (
            db.table("markets")
            .upsert(data, on_conflict="platform,platform_id")
            .execute()
        )
    except Exception:
        logger.exception(
            "DB: failed to upsert market %s/%s", platform, platform_id
        )
        raise
    return MarketRow(**result.data[0])


def get_market(market_id: str) -> Optional[MarketRow]:
    db = get_supabase()
    result = db.table("markets").select("*").eq("id", market_id).execute()
    if result.data:
        return MarketRow(**result.data[0])
    return None


def list_markets(
    platform: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = "active",
    limit: int = 50,
    offset: int = 0,
) -> list[MarketRow]:
    db = get_supabase()
    query = db.table("markets").select("*")
    if platform:
        query = query.eq("platform", platform)
    if category:
        query = query.eq("category", category)
    if status:
        query = query.eq("status", status)
    query = query.order("updated_at", desc=True).range(offset, offset + limit - 1)
    result = query.execute()
    return [MarketRow(**row) for row in result.data]


def count_markets(
    platform: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = "active",
) -> int:
    db = get_supabase()
    query = db.table("markets").select("id", count="exact")
    if platform:
        query = query.eq("platform", platform)
    if category:
        query = query.eq("category", category)
    if status:
        query = query.eq("status", status)
    result = query.execute()
    return result.count or 0


def update_market_status(
    market_id: str, status: str, outcome: Optional[bool] = None
) -> None:
    db = get_supabase()
    data: dict = {"status": status, "updated_at": datetime.utcnow().isoformat()}
    if outcome is not None:
        data["outcome"] = outcome
    db.table("markets").update(data).eq("id", market_id).execute()


def close_markets_by_ids(market_ids: list[str]) -> int:
    """Soft-delete markets by marking them as closed."""
    if not market_ids:
        return 0
    db = get_supabase()
    result = (
        db.table("markets")
        .update({"status": "closed", "updated_at": datetime.utcnow().isoformat()})
        .in_("id", market_ids)
        .execute()
    )
    return len(result.data)


def close_non_kalshi_markets() -> int:
    """Mark all non-Kalshi active markets as closed (app is Kalshi-only now)."""
    db = get_supabase()
    result = (
        db.table("markets")
        .update({"status": "closed", "updated_at": datetime.utcnow().isoformat()})
        .eq("status", "active")
        .neq("platform", "kalshi")
        .execute()
    )
    return len(result.data)


# ── Market Snapshots ──


def insert_snapshot(
    market_id: str,
    price_yes: float,
    price_no: Optional[float] = None,
    volume: Optional[float] = None,
    liquidity: Optional[float] = None,
) -> SnapshotRow:
    db = get_supabase()
    data = {
        "market_id": market_id,
        "price_yes": price_yes,
        "price_no": price_no if price_no is not None else round(1.0 - price_yes, 4),
        "volume": volume,
        "liquidity": liquidity,
    }
    try:
        result = db.table("market_snapshots").insert(data).execute()
    except Exception:
        logger.exception("DB: failed to insert snapshot for market %s", market_id)
        raise
    return SnapshotRow(**result.data[0])


def get_latest_snapshot(market_id: str) -> Optional[SnapshotRow]:
    db = get_supabase()
    result = (
        db.table("market_snapshots")
        .select("*")
        .eq("market_id", market_id)
        .order("captured_at", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return SnapshotRow(**result.data[0])
    return None


def get_snapshots(market_id: str, limit: int = 100) -> list[SnapshotRow]:
    db = get_supabase()
    result = (
        db.table("market_snapshots")
        .select("*")
        .eq("market_id", market_id)
        .order("captured_at", desc=True)
        .limit(limit)
        .execute()
    )
    return [SnapshotRow(**row) for row in result.data]


def get_markets_with_price_movement(
    threshold: float = 0.05,
) -> list[tuple[MarketRow, SnapshotRow, SnapshotRow]]:
    """Find active markets where price moved more than threshold since last snapshot."""
    db = get_supabase()
    markets = list_markets(status="active", limit=500)
    moved = []

    for market in markets:
        snapshots = (
            db.table("market_snapshots")
            .select("*")
            .eq("market_id", market.id)
            .order("captured_at", desc=True)
            .limit(2)
            .execute()
        )
        if len(snapshots.data) >= 2:
            new_snap = SnapshotRow(**snapshots.data[0])
            old_snap = SnapshotRow(**snapshots.data[1])
            if abs(new_snap.price_yes - old_snap.price_yes) >= threshold:
                moved.append((market, old_snap, new_snap))

    return moved


# ── AI Estimates ──


def insert_estimate(
    market_id: str,
    probability: float,
    confidence: str,
    reasoning: str,
    key_evidence: Optional[list[str]] = None,
    key_uncertainties: Optional[list[str]] = None,
    model_used: str = "",
) -> AIEstimateRow:
    db = get_supabase()
    data = {
        "market_id": market_id,
        "probability": probability,
        "confidence": confidence,
        "reasoning": reasoning,
        "key_evidence": key_evidence or [],
        "key_uncertainties": key_uncertainties or [],
        "model_used": model_used,
    }
    try:
        result = db.table("ai_estimates").insert(data).execute()
    except Exception:
        logger.exception("DB: failed to insert estimate for market %s", market_id)
        raise
    return AIEstimateRow(**result.data[0])


def get_latest_estimate(market_id: str) -> Optional[AIEstimateRow]:
    db = get_supabase()
    result = (
        db.table("ai_estimates")
        .select("*")
        .eq("market_id", market_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return AIEstimateRow(**result.data[0])
    return None


def get_estimates(market_id: str, limit: int = 20) -> list[AIEstimateRow]:
    db = get_supabase()
    result = (
        db.table("ai_estimates")
        .select("*")
        .eq("market_id", market_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return [AIEstimateRow(**row) for row in result.data]


# ── Recommendations ──


def insert_recommendation(
    market_id: str,
    estimate_id: str,
    snapshot_id: str,
    direction: str,
    market_price: float,
    ai_probability: float,
    edge: float,
    ev: float,
    kelly_fraction: float,
) -> RecommendationRow:
    db = get_supabase()
    data = {
        "market_id": market_id,
        "estimate_id": estimate_id,
        "snapshot_id": snapshot_id,
        "direction": direction,
        "market_price": market_price,
        "ai_probability": ai_probability,
        "edge": edge,
        "ev": ev,
        "kelly_fraction": kelly_fraction,
    }
    try:
        result = db.table("recommendations").insert(data).execute()
    except Exception:
        logger.exception(
            "DB: failed to insert recommendation for market %s", market_id
        )
        raise
    return RecommendationRow(**result.data[0])


def get_active_recommendations() -> list[RecommendationRow]:
    db = get_supabase()
    result = (
        db.table("recommendations")
        .select("*")
        .eq("status", "active")
        .order("ev", desc=True)
        .execute()
    )
    return [RecommendationRow(**row) for row in result.data]


def get_recommendation_history(
    limit: int = 50, offset: int = 0
) -> list[RecommendationRow]:
    db = get_supabase()
    result = (
        db.table("recommendations")
        .select("*")
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return [RecommendationRow(**row) for row in result.data]


def expire_recommendations(market_id: str) -> None:
    db = get_supabase()
    db.table("recommendations").update({"status": "expired"}).eq(
        "market_id", market_id
    ).eq("status", "active").execute()


def resolve_recommendations(market_id: str) -> None:
    """Mark all active recommendations for a resolved market as 'resolved'."""
    db = get_supabase()
    db.table("recommendations").update({"status": "resolved"}).eq(
        "market_id", market_id
    ).eq("status", "active").execute()


# ── Performance ──


def insert_performance(
    market_id: str,
    ai_probability: float,
    market_price: float,
    actual_outcome: bool,
    brier_score: float,
    recommendation_id: Optional[str] = None,
    pnl: Optional[float] = None,
) -> PerformanceRow:
    db = get_supabase()
    data = {
        "market_id": market_id,
        "recommendation_id": recommendation_id,
        "ai_probability": ai_probability,
        "market_price": market_price,
        "actual_outcome": actual_outcome,
        "pnl": pnl,
        "brier_score": brier_score,
    }
    try:
        result = db.table("performance_log").insert(data).execute()
    except Exception:
        logger.exception(
            "DB: failed to insert performance log for market %s", market_id
        )
        raise
    return PerformanceRow(**result.data[0])


def get_performance_aggregate(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> dict:
    db = get_supabase()
    query = db.table("performance_log").select("*")
    if from_date:
        query = query.gte("resolved_at", from_date)
    if to_date:
        query = query.lte("resolved_at", to_date)
    result = query.execute()
    rows = result.data

    if not rows:
        return {
            "total_resolved": 0,
            "hit_rate": 0.0,
            "avg_brier_score": 0.0,
            "total_pnl": 0.0,
            "avg_edge": 0.0,
        }

    total = len(rows)
    correct = sum(
        1
        for r in rows
        if (r["ai_probability"] >= 0.5 and r["actual_outcome"])
        or (r["ai_probability"] < 0.5 and not r["actual_outcome"])
    )
    avg_brier = sum(r["brier_score"] for r in rows) / total
    total_pnl = sum(r.get("pnl", 0) or 0 for r in rows)

    return {
        "total_resolved": total,
        "hit_rate": round(correct / total, 4) if total > 0 else 0.0,
        "avg_brier_score": round(avg_brier, 4),
        "total_pnl": round(total_pnl, 2),
        "avg_edge": 0.0,
    }


def get_calibration_data(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> list[CalibrationBucket]:
    """Bucket AI probabilities into 10 bins and compute actual resolution frequency."""
    db = get_supabase()
    query = db.table("performance_log").select("*")
    if from_date:
        query = query.gte("resolved_at", from_date)
    if to_date:
        query = query.lte("resolved_at", to_date)
    result = query.execute()
    rows = result.data

    if not rows:
        return []

    buckets: dict[int, list[dict]] = {i: [] for i in range(10)}
    for row in rows:
        prob = row["ai_probability"]
        bucket_idx = min(int(prob * 10), 9)
        buckets[bucket_idx].append(row)

    calibration = []
    for i in range(10):
        bucket_rows = buckets[i]
        if not bucket_rows:
            continue
        predicted_avg = sum(r["ai_probability"] for r in bucket_rows) / len(
            bucket_rows
        )
        actual_freq = sum(1 for r in bucket_rows if r["actual_outcome"]) / len(
            bucket_rows
        )
        calibration.append(
            CalibrationBucket(
                bucket_min=i / 10,
                bucket_max=(i + 1) / 10,
                predicted_avg=round(predicted_avg, 4),
                actual_frequency=round(actual_freq, 4),
                count=len(bucket_rows),
            )
        )

    return calibration


def get_calibration_feedback(category: str | None = None) -> str | None:
    """Build a calibration feedback string from historical prediction data.

    Summarises the AI's own accuracy so it can self-correct over time.
    Returns None if fewer than 5 resolved predictions exist.
    """
    db = get_supabase()

    # Join performance_log with markets for category filtering
    query = db.table("performance_log").select("*, markets!inner(category)")
    if category:
        query = query.eq("markets.category", category)
    result = query.execute()
    rows = result.data

    if not rows or len(rows) < 5:
        return None

    total = len(rows)
    correct = sum(
        1
        for r in rows
        if (r["ai_probability"] >= 0.5 and r["actual_outcome"])
        or (r["ai_probability"] < 0.5 and not r["actual_outcome"])
    )
    accuracy = correct / total
    avg_brier = sum(r["brier_score"] for r in rows) / total

    # Direction bias
    yes_preds = sum(1 for r in rows if r["ai_probability"] >= 0.5)
    yes_outcomes = sum(1 for r in rows if r["actual_outcome"])

    # Calibration by bucket (simplified: low, mid, high)
    buckets = {"low (10-40%)": [], "mid (40-60%)": [], "high (60-90%)": []}
    for r in rows:
        p = r["ai_probability"]
        if p < 0.4:
            buckets["low (10-40%)"].append(r)
        elif p < 0.6:
            buckets["mid (40-60%)"].append(r)
        else:
            buckets["high (60-90%)"].append(r)

    lines = [
        f"Total resolved predictions: {total}",
        f"Overall accuracy: {accuracy:.0%} ({correct}/{total})",
        f"Average Brier score: {avg_brier:.3f} ({'Excellent' if avg_brier <= 0.1 else 'Good' if avg_brier <= 0.15 else 'Fair' if avg_brier <= 0.2 else 'Needs improvement'})",
        f"Direction tendency: You predicted YES {yes_preds}/{total} times, actual YES outcomes: {yes_outcomes}/{total}",
    ]

    for label, bucket_rows in buckets.items():
        if len(bucket_rows) >= 3:
            avg_pred = sum(r["ai_probability"] for r in bucket_rows) / len(bucket_rows)
            actual_freq = sum(1 for r in bucket_rows if r["actual_outcome"]) / len(bucket_rows)
            diff = avg_pred - actual_freq
            bias = "overconfident" if diff > 0.05 else "underconfident" if diff < -0.05 else "well-calibrated"
            lines.append(
                f"Bucket {label}: predicted avg {avg_pred:.0%}, actual {actual_freq:.0%} — {bias}"
            )

    return "\n".join(lines)


# ── Trades ──


def insert_trade(
    market_id: str,
    platform: str,
    direction: str,
    entry_price: float,
    amount: float,
    shares: Optional[float] = None,
    fees_paid: float = 0.0,
    notes: Optional[str] = None,
    recommendation_id: Optional[str] = None,
    source: str = "manual",
    platform_trade_id: Optional[str] = None,
) -> TradeRow:
    db = get_supabase()
    data: dict = {
        "market_id": market_id,
        "platform": platform,
        "direction": direction,
        "entry_price": entry_price,
        "amount": amount,
        "shares": shares,
        "fees_paid": fees_paid,
        "notes": notes,
        "source": source,
        "platform_trade_id": platform_trade_id,
    }
    if recommendation_id:
        data["recommendation_id"] = recommendation_id
    try:
        result = db.table("trades").insert(data).execute()
    except Exception:
        logger.exception(
            "DB: failed to insert trade for market %s (%s)", market_id, platform
        )
        raise
    return TradeRow(**result.data[0])


def get_trade(trade_id: str) -> Optional[TradeRow]:
    db = get_supabase()
    result = db.table("trades").select("*").eq("id", trade_id).execute()
    if result.data:
        return TradeRow(**result.data[0])
    return None


def list_trades(
    status: Optional[str] = None,
    platform: Optional[str] = None,
    market_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TradeRow]:
    db = get_supabase()
    query = db.table("trades").select("*")
    if status:
        query = query.eq("status", status)
    if platform:
        query = query.eq("platform", platform)
    if market_id:
        query = query.eq("market_id", market_id)
    query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
    result = query.execute()
    return [TradeRow(**row) for row in result.data]


def count_trades(
    status: Optional[str] = None,
    platform: Optional[str] = None,
) -> int:
    db = get_supabase()
    query = db.table("trades").select("id", count="exact")
    if status:
        query = query.eq("status", status)
    if platform:
        query = query.eq("platform", platform)
    result = query.execute()
    return result.count or 0


def update_trade(trade_id: str, updates: dict) -> Optional[TradeRow]:
    db = get_supabase()
    result = db.table("trades").update(updates).eq("id", trade_id).execute()
    if result.data:
        return TradeRow(**result.data[0])
    return None


def delete_trade(trade_id: str) -> None:
    db = get_supabase()
    db.table("trades").delete().eq("id", trade_id).execute()


def get_open_trades() -> list[TradeRow]:
    db = get_supabase()
    result = (
        db.table("trades")
        .select("*")
        .eq("status", "open")
        .order("created_at", desc=True)
        .execute()
    )
    return [TradeRow(**row) for row in result.data]


def get_closed_trades(limit: int = 100) -> list[TradeRow]:
    db = get_supabase()
    result = (
        db.table("trades")
        .select("*")
        .eq("status", "closed")
        .order("closed_at", desc=True)
        .limit(limit)
        .execute()
    )
    return [TradeRow(**row) for row in result.data]


def cancel_trades_for_market(market_id: str) -> list[TradeRow]:
    """Cancel all open trades for a voided/cancelled market (no P&L)."""
    open_trades = list_trades(status="open", market_id=market_id)
    cancelled: list[TradeRow] = []

    for trade in open_trades:
        updates = {
            "status": "cancelled",
            "closed_at": datetime.utcnow().isoformat(),
            "notes": ((trade.notes or "") + " [Market cancelled/voided]").strip(),
        }
        updated = update_trade(trade.id, updates)
        if updated:
            cancelled.append(updated)

    return cancelled


def close_trades_for_market(market_id: str, exit_price: float) -> list[TradeRow]:
    """Close all open trades for a resolved market and calculate P&L."""
    open_trades = list_trades(status="open", market_id=market_id)
    closed: list[TradeRow] = []

    for trade in open_trades:
        if trade.direction == "yes":
            if exit_price >= 0.99:  # YES resolved
                pnl = trade.amount * (1.0 - trade.entry_price) / trade.entry_price - trade.fees_paid
            else:
                pnl = -trade.amount - trade.fees_paid
        else:
            if exit_price <= 0.01:  # NO resolved
                no_price = 1.0 - trade.entry_price
                pnl = (trade.amount * trade.entry_price / no_price - trade.fees_paid) if no_price > 0 else -trade.fees_paid
            else:
                pnl = -trade.amount - trade.fees_paid

        updates = {
            "status": "closed",
            "exit_price": exit_price,
            "pnl": round(pnl, 4),
            "closed_at": datetime.utcnow().isoformat(),
        }
        updated = update_trade(trade.id, updates)
        if updated:
            closed.append(updated)

    return closed


# ── Config ──


def get_config() -> dict:
    db = get_supabase()
    result = db.table("config").select("*").execute()

    config = {
        "min_edge_threshold": settings.min_edge_threshold,
        "min_volume": settings.min_volume,
        "kelly_fraction": settings.kelly_fraction,
        "max_single_bet_fraction": settings.max_single_bet_fraction,
        "re_estimate_trigger": settings.re_estimate_trigger,
        "scan_interval_hours": settings.scan_interval_hours,
        "bankroll": settings.bankroll,
        "platforms_enabled": {
            "polymarket": False,
            "kalshi": True,
            "manifold": False,
        },
        "markets_per_platform": settings.markets_per_platform,
        "web_search_max_uses": settings.web_search_max_uses,
        "price_check_enabled": settings.price_check_enabled,
        "price_check_interval_hours": settings.price_check_interval_hours,
        "estimate_cache_hours": settings.estimate_cache_hours,
        "resolution_check_enabled": settings.resolution_check_enabled,
        "resolution_check_interval_hours": settings.resolution_check_interval_hours,
        "trade_sync_enabled": settings.trade_sync_enabled,
        "trade_sync_interval_hours": settings.trade_sync_interval_hours,
        "polymarket_wallet_address": settings.polymarket_wallet_address,
        "kalshi_rsa_configured": bool(
            settings.kalshi_api_key
            and (settings.kalshi_private_key_path or settings.kalshi_private_key)
        ),
    }

    for row in result.data:
        key = row["key"]
        value = row["value"]
        if key in config:
            config[key] = value

    return config


def update_config(updates: dict) -> None:
    db = get_supabase()
    for key, value in updates.items():
        db.table("config").upsert(
            {"key": key, "value": value, "updated_at": datetime.utcnow().isoformat()},
            on_conflict="key",
        ).execute()


# ── Cost Tracking ──


def insert_cost_log(
    model_used: str,
    input_tokens: int,
    output_tokens: int,
    estimated_cost: float,
    scan_id: str | None = None,
    market_id: str | None = None,
) -> CostLogRow:
    db = get_supabase()
    row = {
        "model_used": model_used,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost": estimated_cost,
    }
    if scan_id:
        row["scan_id"] = scan_id
    if market_id:
        row["market_id"] = market_id

    try:
        result = db.table("cost_log").insert(row).execute()
    except Exception:
        logger.exception("DB: failed to insert cost log entry")
        raise
    return CostLogRow(**result.data[0])


def get_cost_summary() -> dict:
    db = get_supabase()
    result = db.table("cost_log").select("*").order(
        "created_at", desc=True
    ).limit(10000).execute()

    rows = result.data
    now = datetime.utcnow()

    total_all = 0.0
    total_today = 0.0
    total_week = 0.0
    total_month = 0.0
    total_calls = len(rows)

    for row in rows:
        cost = float(row.get("estimated_cost", 0))
        total_all += cost
        created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")).replace(tzinfo=None)
        days_ago = (now - created).days
        if days_ago < 1:
            total_today += cost
        if days_ago < 7:
            total_week += cost
        if days_ago < 30:
            total_month += cost

    scan_ids = {r["scan_id"] for r in rows if r.get("scan_id")}
    cost_per_scan = total_all / len(scan_ids) if scan_ids else 0.0

    return {
        "total_cost_today": round(total_today, 6),
        "total_cost_week": round(total_week, 6),
        "total_cost_month": round(total_month, 6),
        "total_cost_all_time": round(total_all, 6),
        "cost_per_scan_avg": round(cost_per_scan, 6),
        "total_api_calls": total_calls,
    }
