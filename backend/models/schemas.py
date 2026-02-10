from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums ──


class Platform(str, Enum):
    polymarket = "polymarket"
    kalshi = "kalshi"
    manifold = "manifold"
    metaculus = "metaculus"


class MarketStatus(str, Enum):
    active = "active"
    closed = "closed"
    resolved = "resolved"


class Confidence(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class Direction(str, Enum):
    yes = "yes"
    no = "no"


class RecommendationStatus(str, Enum):
    active = "active"
    expired = "expired"
    resolved = "resolved"


# ── Database row models ──


class MarketRow(BaseModel):
    id: str
    platform: str
    platform_id: str
    question: str
    description: Optional[str] = None
    resolution_criteria: Optional[str] = None
    category: Optional[str] = None
    close_date: Optional[datetime] = None
    status: str = "active"
    outcome: Optional[bool] = None
    created_at: datetime
    updated_at: datetime


class SnapshotRow(BaseModel):
    id: str
    market_id: str
    price_yes: float
    price_no: Optional[float] = None
    volume: Optional[float] = None
    liquidity: Optional[float] = None
    captured_at: datetime


class AIEstimateRow(BaseModel):
    id: str
    market_id: str
    probability: float
    confidence: str
    reasoning: str
    key_evidence: Optional[list[str]] = None
    key_uncertainties: Optional[list[str]] = None
    model_used: str
    created_at: datetime


class RecommendationRow(BaseModel):
    id: str
    market_id: str
    estimate_id: str
    snapshot_id: str
    direction: str
    market_price: float
    ai_probability: float
    edge: float
    ev: float
    kelly_fraction: float
    status: str = "active"
    created_at: datetime


class PerformanceRow(BaseModel):
    id: str
    market_id: str
    recommendation_id: Optional[str] = None
    ai_probability: float
    market_price: float
    actual_outcome: bool
    pnl: Optional[float] = None
    brier_score: float
    resolved_at: datetime


# ── API response models ──


class MarketListResponse(BaseModel):
    markets: list[MarketRow]
    total: int


class MarketDetailResponse(BaseModel):
    market: MarketRow
    latest_snapshot: Optional[SnapshotRow] = None
    latest_estimate: Optional[AIEstimateRow] = None
    latest_recommendation: Optional[RecommendationRow] = None


class RecommendationWithMarket(BaseModel):
    recommendation: RecommendationRow
    market: MarketRow


class RecommendationListResponse(BaseModel):
    recommendations: list[RecommendationRow]
    markets: dict[str, MarketRow]


class PerformanceAggregateResponse(BaseModel):
    total_resolved: int = 0
    hit_rate: float = 0.0
    avg_brier_score: float = 0.0
    total_pnl: float = 0.0
    avg_edge: float = 0.0


class CalibrationBucket(BaseModel):
    bucket_min: float
    bucket_max: float
    predicted_avg: float
    actual_frequency: float
    count: int


class CalibrationResponse(BaseModel):
    buckets: list[CalibrationBucket]


class ConfigResponse(BaseModel):
    min_edge_threshold: float
    min_volume: float
    kelly_fraction: float
    max_single_bet_fraction: float
    re_estimate_trigger: float
    scan_interval_hours: int
    bankroll: float
    platforms_enabled: dict[str, bool]


class ConfigUpdateRequest(BaseModel):
    min_edge_threshold: Optional[float] = None
    min_volume: Optional[float] = None
    kelly_fraction: Optional[float] = None
    max_single_bet_fraction: Optional[float] = None
    re_estimate_trigger: Optional[float] = None
    scan_interval_hours: Optional[int] = None
    bankroll: Optional[float] = None
    platforms_enabled: Optional[dict[str, bool]] = None


class ScanStatusResponse(BaseModel):
    status: str  # "running", "completed", "failed"
    platform: Optional[str] = None
    markets_found: int = 0
    markets_researched: int = 0
    recommendations_created: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class HealthResponse(BaseModel):
    status: str
    last_scan_at: Optional[datetime] = None
    database_connected: bool = False
    platforms: dict[str, bool] = {}


# ── Internal pipeline models (NOT exposed via API) ──


class BlindMarketInput(BaseModel):
    """What gets passed to Claude — NO PRICES, NO VOLUME, NO MARKET DATA."""

    question: str
    resolution_criteria: Optional[str] = None
    close_date: Optional[str] = None
    category: Optional[str] = None


class AIEstimateOutput(BaseModel):
    """Structured output from Claude."""

    reasoning: str
    probability: float = Field(ge=0.01, le=0.99)
    confidence: Confidence
    key_evidence: list[str] = []
    key_uncertainties: list[str] = []
