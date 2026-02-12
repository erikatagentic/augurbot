"use client";

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { fetchRecommendations, fetchRecommendationsHistory, triggerScan, triggerResolutionCheck, triggerTradeSync, fetchTradeSyncStatus, fetchScanProgress } from "@/lib/api";
import type { RecommendationListResponse, TradeSyncStatus, ScanProgress } from "@/lib/types";

export function useRecommendations() {
  const { data, error, isLoading, mutate } = useSWR<RecommendationListResponse>(
    "/api/recommendations",
    () => fetchRecommendations(),
    { refreshInterval: 60000 }
  );
  return { data, error, isLoading, mutate };
}

export function useRecommendationsHistory() {
  const { data, error, isLoading } = useSWR<RecommendationListResponse>(
    "/api/recommendations/history",
    () => fetchRecommendationsHistory()
  );
  return { data, error, isLoading };
}

export function useScanTrigger() {
  const { trigger, isMutating } = useSWRMutation("/api/scan", () => triggerScan());
  return { trigger, isScanning: isMutating };
}

export function useScanProgress(enabled: boolean) {
  const { data, error, isLoading, mutate } = useSWR<ScanProgress>(
    enabled ? "/api/scan/progress" : null,
    () => fetchScanProgress(),
    { refreshInterval: enabled ? 2000 : 0 }
  );
  return { data, error, isLoading, mutate };
}

export function useResolutionCheckTrigger() {
  const { trigger, isMutating } = useSWRMutation("/api/resolutions/check", () => triggerResolutionCheck());
  return { trigger, isChecking: isMutating };
}

export function useTradeSyncTrigger() {
  const { trigger, isMutating } = useSWRMutation("/api/trades/sync", () => triggerTradeSync());
  return { trigger, isSyncing: isMutating };
}

export function useTradeSyncStatus() {
  const { data, error, isLoading, mutate } = useSWR<TradeSyncStatus>(
    "/api/trades/sync/status",
    () => fetchTradeSyncStatus(),
  );
  return { data, error, isLoading, mutate };
}
