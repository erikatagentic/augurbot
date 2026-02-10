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
