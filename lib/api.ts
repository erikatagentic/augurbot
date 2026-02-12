import type {
  MarketDetail,
  MarketListResponse,
  MarketFilters,
  AIEstimate,
  MarketSnapshot,
  Recommendation,
  RecommendationListResponse,
  PerformanceStats,
  CalibrationBucket,
  ScanStatus,
  AppConfig,
  HealthStatus,
  Platform,
  Trade,
  TradeCreateInput,
  TradeUpdateInput,
  TradeListResponse,
  TradeWithMarket,
  PortfolioStats,
  AIvsActualComparison,
  CostSummary,
  ResolutionCheckStatus,
  TradeSyncStatus,
  ExecuteTradeResponse,
} from "@/lib/types";

// Production: Railway backend; local dev: overridden by .env.local
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  "https://augurbot-production.up.railway.app";

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "Unknown error");
    throw new ApiError(
      `API request failed: ${res.status} ${res.statusText} - ${body}`,
      res.status
    );
  }

  return res.json() as Promise<T>;
}

function buildQueryString(
  params: Record<string, string | number | boolean | undefined>
): string {
  const entries = Object.entries(params).filter(
    ([, value]) => value !== undefined && value !== ""
  );
  if (entries.length === 0) return "";
  const searchParams = new URLSearchParams();
  for (const [key, value] of entries) {
    searchParams.set(key, String(value));
  }
  return `?${searchParams.toString()}`;
}

// ── Markets ──

export async function fetchMarkets(
  filters?: MarketFilters
): Promise<MarketListResponse> {
  const query = filters ? buildQueryString(filters as Record<string, string | number | boolean | undefined>) : "";
  return apiFetch<MarketListResponse>(`/markets${query}`);
}

export async function fetchMarketDetail(
  id: string
): Promise<MarketDetail> {
  return apiFetch<MarketDetail>(`/markets/${id}`);
}

export async function fetchMarketEstimates(
  id: string
): Promise<AIEstimate[]> {
  return apiFetch<AIEstimate[]>(`/markets/${id}/estimates`);
}

export async function fetchMarketSnapshots(
  id: string
): Promise<MarketSnapshot[]> {
  return apiFetch<MarketSnapshot[]>(`/markets/${id}/snapshots`);
}

export async function refreshMarketEstimate(
  id: string
): Promise<AIEstimate> {
  return apiFetch<AIEstimate>(`/markets/${id}/refresh`, {
    method: "POST",
  });
}

// ── Recommendations ──

export async function fetchRecommendations(): Promise<RecommendationListResponse> {
  return apiFetch<RecommendationListResponse>("/recommendations");
}

export async function fetchRecommendationsHistory(): Promise<RecommendationListResponse> {
  return apiFetch<RecommendationListResponse>("/recommendations/history");
}

// ── Performance ──

export async function fetchPerformance(params?: {
  from_date?: string;
  to_date?: string;
}): Promise<PerformanceStats> {
  const query = params
    ? buildQueryString(params as Record<string, string | number | boolean | undefined>)
    : "";
  return apiFetch<PerformanceStats>(`/performance${query}`);
}

export async function fetchCalibration(params?: {
  from_date?: string;
  to_date?: string;
}): Promise<CalibrationBucket[]> {
  const query = params
    ? buildQueryString(params as Record<string, string | number | boolean | undefined>)
    : "";
  return apiFetch<CalibrationBucket[]>(`/performance/calibration${query}`);
}

export async function fetchCostSummary(): Promise<CostSummary> {
  return apiFetch<CostSummary>("/performance/costs");
}

// ── Scan ──

export async function triggerScan(): Promise<ScanStatus> {
  return apiFetch<ScanStatus>("/scan", { method: "POST" });
}

export async function triggerPlatformScan(
  platform: Platform
): Promise<ScanStatus> {
  return apiFetch<ScanStatus>(`/scan/${platform}`, { method: "POST" });
}

// ── Resolution ──

export async function triggerResolutionCheck(): Promise<ResolutionCheckStatus> {
  return apiFetch<ResolutionCheckStatus>("/resolutions/check", {
    method: "POST",
  });
}

export async function manuallyResolveMarket(
  marketId: string,
  outcome: boolean
): Promise<{ status: string; market_id: string; outcome: boolean }> {
  return apiFetch(`/markets/${marketId}/resolve`, {
    method: "POST",
    body: JSON.stringify({ outcome }),
  });
}

// ── Config ──

export async function fetchConfig(): Promise<AppConfig> {
  return apiFetch<AppConfig>("/config");
}

export async function updateConfig(
  config: Partial<AppConfig>
): Promise<AppConfig> {
  return apiFetch<AppConfig>("/config", {
    method: "PUT",
    body: JSON.stringify(config),
  });
}

// ── Trades ──

export async function createTrade(
  trade: TradeCreateInput
): Promise<Trade> {
  return apiFetch<Trade>("/trades", {
    method: "POST",
    body: JSON.stringify(trade),
  });
}

export async function fetchTrades(params?: {
  status?: string;
  platform?: string;
  limit?: number;
  offset?: number;
}): Promise<TradeListResponse> {
  const query = params
    ? buildQueryString(
        params as Record<string, string | number | boolean | undefined>
      )
    : "";
  return apiFetch<TradeListResponse>(`/trades${query}`);
}

export async function fetchOpenTrades(): Promise<TradeListResponse> {
  return apiFetch<TradeListResponse>("/trades/open");
}

export async function fetchTradeDetail(
  id: string
): Promise<TradeWithMarket> {
  return apiFetch<TradeWithMarket>(`/trades/${id}`);
}

export async function updateTrade(
  id: string,
  updates: TradeUpdateInput
): Promise<Trade> {
  return apiFetch<Trade>(`/trades/${id}`, {
    method: "PATCH",
    body: JSON.stringify(updates),
  });
}

export async function deleteTrade(id: string): Promise<void> {
  await apiFetch<{ status: string }>(`/trades/${id}`, { method: "DELETE" });
}

export async function triggerTradeSync(): Promise<{ status: string }> {
  return apiFetch<{ status: string }>("/trades/sync", { method: "POST" });
}

export async function fetchTradeSyncStatus(): Promise<TradeSyncStatus> {
  return apiFetch<TradeSyncStatus>("/trades/sync/status");
}

export async function executeTrade(
  recommendationId: string,
  amount: number
): Promise<ExecuteTradeResponse> {
  return apiFetch<ExecuteTradeResponse>("/trades/execute", {
    method: "POST",
    body: JSON.stringify({
      recommendation_id: recommendationId,
      amount,
    }),
  });
}

export async function fetchPortfolioStats(): Promise<PortfolioStats> {
  return apiFetch<PortfolioStats>("/trades/portfolio");
}

export async function fetchAIvsActual(): Promise<AIvsActualComparison> {
  return apiFetch<AIvsActualComparison>("/trades/comparison");
}

// ── Health ──

export async function fetchHealth(): Promise<HealthStatus> {
  return apiFetch<HealthStatus>("/health");
}

export { ApiError };
