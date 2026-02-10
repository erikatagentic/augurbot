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
    result = (
        db.table("markets")
        .upsert(data, on_conflict="platform,platform_id")
        .execute()
    )
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
    result = db.table("market_snapshots").insert(data).execute()
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
    result = db.table("ai_estimates").insert(data).execute()
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
    result = db.table("recommendations").insert(data).execute()
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
    result = db.table("performance_log").insert(data).execute()
    return PerformanceRow(**result.data[0])


def get_performance_aggregate() -> dict:
    db = get_supabase()
    result = db.table("performance_log").select("*").execute()
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


def get_calibration_data() -> list[CalibrationBucket]:
    """Bucket AI probabilities into 10 bins and compute actual resolution frequency."""
    db = get_supabase()
    result = db.table("performance_log").select("*").execute()
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
            "polymarket": True,
            "manifold": True,
            "kalshi": bool(settings.kalshi_email),
        },
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
