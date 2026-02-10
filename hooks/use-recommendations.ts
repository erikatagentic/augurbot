"use client";

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { fetchRecommendations, fetchRecommendationsHistory, triggerScan } from "@/lib/api";
import type { RecommendationListResponse } from "@/lib/types";

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
