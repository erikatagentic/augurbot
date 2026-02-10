"use client";

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { fetchRecommendations, fetchRecommendationsHistory, triggerScan, triggerResolutionCheck, triggerTradeSync, fetchTradeSyncStatus } from "@/lib/api";
import type { RecommendationListResponse, TradeSyncStatus } from "@/lib/types";

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
