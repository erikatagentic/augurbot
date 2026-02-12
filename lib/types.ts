export type Platform = "polymarket" | "kalshi" | "manifold" | "metaculus";
export type MarketStatus = "active" | "closed" | "resolved";
export type Confidence = "high" | "medium" | "low";
export type Direction = "yes" | "no";
export type RecommendationStatus = "active" | "expired" | "resolved";

export interface Market {
  id: string;
  platform: Platform;
  platform_id: string;
  question: string;
  description: string | null;
  resolution_criteria: string | null;
  category: string | null;
  close_date: string | null;
  outcome_label: string | null;
  status: MarketStatus;
  outcome: boolean | null;
  created_at: string;
  updated_at: string;
}

export interface MarketSnapshot {
  id: string;
  market_id: string;
  price_yes: number;
  price_no: number | null;
  volume: number | null;
  liquidity: number | null;
  captured_at: string;
}

export interface AIEstimate {
  id: string;
  market_id: string;
  probability: number;
  confidence: Confidence;
  reasoning: string;
  key_evidence: string[];
  key_uncertainties: string[];
  model_used: string;
  created_at: string;
}

export interface Recommendation {
  id: string;
  market_id: string;
  estimate_id: string;
  snapshot_id: string;
  direction: Direction;
  market_price: number;
  ai_probability: number;
  edge: number;
  ev: number;
  kelly_fraction: number;
  status: RecommendationStatus;
  created_at: string;
}

export interface PerformanceStats {
  total_resolved: number;
  hit_rate: number;
  avg_brier_score: number;
  total_pnl: number;
  avg_edge: number;
}

export interface CalibrationBucket {
  bucket_min: number;
  bucket_max: number;
  predicted_avg: number;
  actual_frequency: number;
  count: number;
}

export interface AppConfig {
  min_edge_threshold: number;
  min_volume: number;
  kelly_fraction: number;
  max_single_bet_fraction: number;
  re_estimate_trigger: number;
  scan_interval_hours: number;
  bankroll: number;
  platforms_enabled: Record<string, boolean>;
  markets_per_platform: number;
  web_search_max_uses: number;
  price_check_enabled: boolean;
  price_check_interval_hours: number;
  estimate_cache_hours: number;
  resolution_check_enabled: boolean;
  resolution_check_interval_hours: number;
  trade_sync_enabled: boolean;
  trade_sync_interval_hours: number;
  polymarket_wallet_address: string;
  kalshi_rsa_configured: boolean;
  auto_trade_enabled: boolean;
  auto_trade_min_ev: number;
}

export interface ResolutionCheckStatus {
  status: string;
  markets_checked: number;
  markets_resolved: number;
  markets_cancelled: number;
}

export interface CostSummary {
  total_cost_today: number;
  total_cost_week: number;
  total_cost_month: number;
  total_cost_all_time: number;
  cost_per_scan_avg: number;
  total_api_calls: number;
}

export interface HealthStatus {
  status: string;
  last_scan_at: string | null;
  database_connected: boolean;
  platforms: Record<string, boolean>;
}

export interface MarketDetail {
  market: Market;
  latest_snapshot: MarketSnapshot | null;
  latest_estimate: AIEstimate | null;
  latest_recommendation: Recommendation | null;
}

export interface MarketListResponse {
  markets: Market[];
  total: number;
}

export interface RecommendationListResponse {
  recommendations: Recommendation[];
  markets: Record<string, Market>;
}

export interface ScanStatus {
  status: string;
  platform: string | null;
  markets_found: number;
  markets_researched: number;
  recommendations_created: number;
  started_at: string | null;
  completed_at: string | null;
}

export interface MarketFilters {
  platform?: Platform;
  category?: string;
  status?: MarketStatus;
  search?: string;
  limit?: number;
  offset?: number;
}

// ── Trades ──

export type TradeStatus = "open" | "closed" | "cancelled";
export type TradeSource = "manual" | "api_sync";

export interface Trade {
  id: string;
  market_id: string;
  recommendation_id: string | null;
  platform: Platform;
  direction: Direction;
  entry_price: number;
  amount: number;
  shares: number | null;
  status: TradeStatus;
  exit_price: number | null;
  pnl: number | null;
  fees_paid: number;
  notes: string | null;
  source: TradeSource;
  platform_trade_id: string | null;
  created_at: string;
  closed_at: string | null;
}

export interface TradeCreateInput {
  market_id: string;
  recommendation_id?: string;
  platform: Platform;
  direction: Direction;
  entry_price: number;
  amount: number;
  shares?: number;
  fees_paid?: number;
  notes?: string;
}

export interface TradeUpdateInput {
  status?: TradeStatus;
  exit_price?: number;
  pnl?: number;
  fees_paid?: number;
  notes?: string;
}

export interface TradeListResponse {
  trades: Trade[];
  markets: Record<string, Market>;
  total: number;
}

export interface TradeWithMarket {
  trade: Trade;
  market: Market;
}

export interface PortfolioStats {
  open_positions: number;
  total_invested: number;
  unrealized_pnl: number;
  realized_pnl: number;
  total_pnl: number;
  total_trades: number;
  win_rate: number;
  avg_return: number;
}

export interface TradeSyncStatus {
  platforms: Record<string, {
    id: string;
    platform: string;
    status: string;
    trades_found: number;
    trades_created: number;
    trades_updated: number;
    trades_skipped: number;
    error_message: string | null;
    started_at: string | null;
    completed_at: string | null;
  }>;
}

export interface ExecuteTradeResponse {
  status: string;
  trade_id: string;
  order: Record<string, unknown>;
  contracts: number;
  price_cents: number;
  total_cost: number;
  direction: Direction;
  market: string;
}

export interface AIvsActualComparison {
  total_ai_recommendations: number;
  recommendations_traded: number;
  recommendations_not_traded: number;
  ai_hit_rate: number;
  actual_hit_rate: number;
  ai_avg_edge: number;
  actual_avg_return: number;
  ai_brier_score: number;
  comparison_rows: Array<{
    market_id: string;
    question: string;
    trade_direction: Direction;
    trade_pnl: number | null;
    trade_return: number;
    ai_direction: Direction | null;
    ai_edge: number | null;
    followed_ai: boolean | null;
  }>;
}
