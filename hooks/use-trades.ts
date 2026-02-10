"use client";

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import {
  fetchTrades,
  fetchOpenTrades,
  fetchPortfolioStats,
  fetchAIvsActual,
  createTrade,
  updateTrade,
  deleteTrade,
} from "@/lib/api";
import type {
  TradeListResponse,
  PortfolioStats,
  AIvsActualComparison,
  TradeCreateInput,
  TradeUpdateInput,
} from "@/lib/types";

export function useTrades(status?: string) {
  const { data, error, isLoading, mutate } = useSWR<TradeListResponse>(
    status ? `/trades?status=${status}` : "/trades",
    () => fetchTrades(status ? { status } : undefined),
    { refreshInterval: 60_000 }
  );
  return { data, error, isLoading, mutate };
}

export function useOpenTrades() {
  const { data, error, isLoading, mutate } = useSWR<TradeListResponse>(
    "/trades/open",
    () => fetchOpenTrades(),
    { refreshInterval: 60_000 }
  );
  return { data, error, isLoading, mutate };
}

export function usePortfolioStats() {
  const { data, error, isLoading, mutate } = useSWR<PortfolioStats>(
    "/trades/portfolio",
    () => fetchPortfolioStats(),
    { refreshInterval: 60_000 }
  );
  return { data, error, isLoading, mutate };
}

export function useAIvsActual() {
  const { data, error, isLoading } = useSWR<AIvsActualComparison>(
    "/trades/comparison",
    () => fetchAIvsActual()
  );
  return { data, error, isLoading };
}

export function useCreateTrade() {
  const { trigger, isMutating } = useSWRMutation(
    "/trades",
    (_key: string, { arg }: { arg: TradeCreateInput }) => createTrade(arg)
  );
  return { trigger, isCreating: isMutating };
}

export function useUpdateTrade(tradeId: string) {
  const { trigger, isMutating } = useSWRMutation(
    `/trades/${tradeId}`,
    (_key: string, { arg }: { arg: TradeUpdateInput }) =>
      updateTrade(tradeId, arg)
  );
  return { trigger, isUpdating: isMutating };
}

export function useDeleteTrade() {
  const { trigger, isMutating } = useSWRMutation(
    "/trades/delete",
    (_key: string, { arg }: { arg: string }) => deleteTrade(arg)
  );
  return { trigger, isDeleting: isMutating };
}
