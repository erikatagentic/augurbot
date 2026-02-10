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
} from "@/lib/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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

export async function fetchPerformance(): Promise<PerformanceStats> {
  return apiFetch<PerformanceStats>("/performance");
}

export async function fetchCalibration(): Promise<CalibrationBucket[]> {
  return apiFetch<CalibrationBucket[]>("/performance/calibration");
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

// ── Health ──

export async function fetchHealth(): Promise<HealthStatus> {
  return apiFetch<HealthStatus>("/health");
}

export { ApiError };
