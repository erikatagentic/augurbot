"use client";

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import {
  fetchMarkets,
  fetchMarketDetail,
  fetchMarketEstimates,
  fetchMarketSnapshots,
  refreshMarketEstimate,
} from "@/lib/api";
import type {
  MarketListResponse,
  MarketDetail,
  AIEstimate,
  MarketSnapshot,
  MarketFilters,
} from "@/lib/types";

function serializeFilters(filters?: MarketFilters): string {
  if (!filters) return "/api/markets";
  const parts = Object.entries(filters)
    .filter(([, v]) => v !== undefined && v !== "")
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k}=${String(v)}`)
    .join("&");
  return parts ? `/api/markets?${parts}` : "/api/markets";
}

export function useMarkets(filters?: MarketFilters) {
  const { data, error, isLoading, mutate } = useSWR<MarketListResponse>(
    serializeFilters(filters),
    () => fetchMarkets(filters)
  );
  return { data, error, isLoading, mutate };
}

export function useMarketDetail(id: string) {
  const { data, error, isLoading, mutate } = useSWR<MarketDetail>(
    id ? `/api/markets/${id}` : null,
    () => fetchMarketDetail(id)
  );
  return { data, error, isLoading, mutate };
}

export function useMarketEstimates(id: string) {
  const { data, error, isLoading, mutate } = useSWR<AIEstimate[]>(
    id ? `/api/markets/${id}/estimates` : null,
    () => fetchMarketEstimates(id)
  );
  return { data, error, isLoading, mutate };
}

export function useMarketSnapshots(id: string) {
  const { data, error, isLoading } = useSWR<MarketSnapshot[]>(
    id ? `/api/markets/${id}/snapshots` : null,
    () => fetchMarketSnapshots(id)
  );
  return { data, error, isLoading };
}

export function useRefreshEstimate(id: string) {
  const { trigger, isMutating } = useSWRMutation(
    id ? `/api/markets/${id}/refresh` : null,
    () => refreshMarketEstimate(id)
  );
  return { trigger, isRefreshing: isMutating };
}
