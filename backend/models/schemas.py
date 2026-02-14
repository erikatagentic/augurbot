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


class TradeStatus(str, Enum):
    open = "open"
    closed = "closed"
    cancelled = "cancelled"


class TradeSource(str, Enum):
    manual = "manual"
    api_sync = "api_sync"


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
    outcome_label: Optional[str] = None
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
    simulated_pnl: Optional[float] = None
    brier_score: float
    resolved_at: datetime


class TradeRow(BaseModel):
    id: str
    market_id: str
    recommendation_id: Optional[str] = None
    platform: str
    direction: str
    entry_price: float
    amount: float
    shares: Optional[float] = None
    status: str = "open"
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    fees_paid: float = 0.0
    notes: Optional[str] = None
    source: str = "manual"
    platform_trade_id: Optional[str] = None
    created_at: datetime
    closed_at: Optional[datetime] = None


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
    total_simulated_pnl: float = 0.0


class CalibrationBucket(BaseModel):
    bucket_min: float
    bucket_max: float
    predicted_avg: float
    actual_frequency: float
    count: int


class CalibrationResponse(BaseModel):
    buckets: list[CalibrationBucket]


class TradeSyncStatusResponse(BaseModel):
    platforms: dict[str, dict] = {}


class ConfigResponse(BaseModel):
    min_edge_threshold: float
    min_volume: float
    kelly_fraction: float
    max_single_bet_fraction: float
    max_exposure_fraction: float = 0.25
    max_event_exposure_fraction: float = 0.10
    re_estimate_trigger: float
    scan_interval_hours: int
    bankroll: float
    platforms_enabled: dict[str, bool]
    markets_per_platform: int = 25
    web_search_max_uses: int = 3
    price_check_enabled: bool = False
    price_check_interval_hours: int = 6
    estimate_cache_hours: float = 20.0
    resolution_check_enabled: bool = True
    resolution_check_interval_hours: int = 6
    trade_sync_enabled: bool = False
    trade_sync_interval_hours: int = 4
    polymarket_wallet_address: str = ""
    kalshi_rsa_configured: bool = False
    auto_trade_enabled: bool = False
    auto_trade_min_ev: float = 0.05
    max_close_hours: int = 24
    notifications_enabled: bool = False
    notification_email: str = ""
    notification_slack_webhook: str = ""
    notification_min_ev: float = 0.08
    daily_digest_enabled: bool = True
    scan_times: list[int] = [8, 14]
    use_premium_model: bool = False


class ConfigUpdateRequest(BaseModel):
    min_edge_threshold: Optional[float] = Field(None, ge=0.01, le=0.5)
    min_volume: Optional[float] = Field(None, gt=0)
    kelly_fraction: Optional[float] = Field(None, gt=0, le=0.5)
    max_single_bet_fraction: Optional[float] = Field(None, gt=0, le=0.25)
    max_exposure_fraction: Optional[float] = Field(None, gt=0, le=1.0)
    max_event_exposure_fraction: Optional[float] = Field(None, gt=0, le=0.5)
    re_estimate_trigger: Optional[float] = Field(None, ge=0.01, le=0.5)
    scan_interval_hours: Optional[int] = Field(None, ge=1, le=168)
    bankroll: Optional[float] = Field(None, gt=0)
    platforms_enabled: Optional[dict[str, bool]] = None
    markets_per_platform: Optional[int] = Field(None, ge=1, le=100)
    web_search_max_uses: Optional[int] = Field(None, ge=0, le=10)
    price_check_enabled: Optional[bool] = None
    price_check_interval_hours: Optional[int] = Field(None, ge=1, le=24)
    estimate_cache_hours: Optional[float] = Field(None, ge=1.0, le=168.0)
    resolution_check_enabled: Optional[bool] = None
    resolution_check_interval_hours: Optional[int] = Field(None, ge=1, le=24)
    trade_sync_enabled: Optional[bool] = None
    trade_sync_interval_hours: Optional[int] = Field(None, ge=1, le=24)
    polymarket_wallet_address: Optional[str] = None
    auto_trade_enabled: Optional[bool] = None
    auto_trade_min_ev: Optional[float] = Field(None, ge=0.01, le=0.5)
    max_close_hours: Optional[int] = Field(None, ge=6, le=168)
    notifications_enabled: Optional[bool] = None
    notification_email: Optional[str] = None
    notification_slack_webhook: Optional[str] = None
    notification_min_ev: Optional[float] = Field(None, ge=0.01, le=0.5)
    daily_digest_enabled: Optional[bool] = None
    scan_times: Optional[list[int]] = None
    use_premium_model: Optional[bool] = None


class ScanStatusResponse(BaseModel):
    status: str  # "running", "completed", "failed"
    platform: Optional[str] = None
    markets_found: int = 0
    markets_researched: int = 0
    recommendations_created: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ScanProgressResponse(BaseModel):
    is_running: bool = False
    phase: str = "idle"
    platform: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    markets_found: int = 0
    markets_total: int = 0
    markets_processed: int = 0
    markets_researched: int = 0
    markets_skipped: int = 0
    recommendations_created: int = 0
    current_market: Optional[str] = None
    error: Optional[str] = None
    elapsed_seconds: Optional[float] = None
    estimated_remaining_seconds: Optional[float] = None


class ResolutionCheckResponse(BaseModel):
    status: str  # "running" or "completed"
    markets_checked: int = 0
    markets_resolved: int = 0
    markets_cancelled: int = 0


class ManualResolveRequest(BaseModel):
    outcome: bool  # True = YES resolved, False = NO resolved


class ExecuteTradeRequest(BaseModel):
    recommendation_id: str
    amount: float = Field(gt=0, description="Dollar amount to bet")


class PnLDataPoint(BaseModel):
    resolved_at: datetime
    pnl: float
    cumulative_pnl: float
    simulated_pnl: float = 0.0
    cumulative_simulated_pnl: float = 0.0


class PnLTimeSeriesResponse(BaseModel):
    data_points: list[PnLDataPoint]


class CategoryPerformance(BaseModel):
    category: str
    total_resolved: int
    hit_rate: float
    avg_brier_score: float
    total_pnl: float = 0.0
    total_simulated_pnl: float = 0.0


class CategoryPerformanceResponse(BaseModel):
    categories: list[CategoryPerformance]


class HealthResponse(BaseModel):
    status: str
    last_scan_at: Optional[datetime] = None
    next_scan_at: Optional[datetime] = None
    database_connected: bool = False
    platforms: dict[str, bool] = {}


# ── Trade request/response models ──


class TradeCreateRequest(BaseModel):
    market_id: str
    recommendation_id: Optional[str] = None
    platform: Platform
    direction: Direction
    entry_price: float = Field(ge=0.01, le=0.99)
    amount: float = Field(gt=0)
    shares: Optional[float] = None
    fees_paid: float = Field(ge=0, default=0)
    notes: Optional[str] = None


class TradeUpdateRequest(BaseModel):
    status: Optional[TradeStatus] = None
    exit_price: Optional[float] = Field(None, ge=0, le=1.0)
    pnl: Optional[float] = None
    fees_paid: Optional[float] = None
    notes: Optional[str] = None


class TradeWithMarket(BaseModel):
    trade: TradeRow
    market: MarketRow


class TradeListResponse(BaseModel):
    trades: list[TradeRow]
    markets: dict[str, MarketRow]
    total: int


class PortfolioStatsResponse(BaseModel):
    open_positions: int = 0
    total_invested: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    total_pnl: float = 0.0
    total_trades: int = 0
    win_rate: float = 0.0
    avg_return: float = 0.0


class AIvsActualResponse(BaseModel):
    total_ai_recommendations: int = 0
    recommendations_traded: int = 0
    recommendations_not_traded: int = 0
    ai_hit_rate: float = 0.0
    actual_hit_rate: float = 0.0
    ai_avg_edge: float = 0.0
    actual_avg_return: float = 0.0
    ai_brier_score: float = 0.0
    comparison_rows: list[dict] = []


# ── Internal pipeline models (NOT exposed via API) ──


class BlindMarketInput(BaseModel):
    """What gets passed to Claude — NO PRICES, NO VOLUME, NO MARKET DATA."""

    question: str
    resolution_criteria: Optional[str] = None
    close_date: Optional[str] = None
    category: Optional[str] = None
    sport_type: Optional[str] = None
    calibration_feedback: Optional[str] = None


class PreparedMarket(BaseModel):
    """Market ready for AI estimation — prepared by _prepare_market()."""

    market_id: str
    market_data: dict
    snapshot_id: str
    snapshot_price_yes: float
    blind_input: BlindMarketInput
    volume: Optional[float] = None
    scan_id: Optional[str] = None


class AIEstimateOutput(BaseModel):
    """Structured output from Claude."""

    reasoning: str
    probability: float = Field(ge=0.01, le=0.99)
    confidence: Confidence
    key_evidence: list[str] = []
    key_uncertainties: list[str] = []
    # Cost tracking (populated by researcher, stored in cost_log)
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0


class CostLogRow(BaseModel):
    id: str
    scan_id: Optional[str] = None
    market_id: Optional[str] = None
    model_used: str
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0
    created_at: datetime


class CostSummaryResponse(BaseModel):
    total_cost_today: float = 0.0
    total_cost_week: float = 0.0
    total_cost_month: float = 0.0
    total_cost_all_time: float = 0.0
    cost_per_scan_avg: float = 0.0
    total_api_calls: int = 0
