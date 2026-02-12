"use client";

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import {
  fetchPerformance,
  fetchCalibration,
  fetchHealth,
  fetchConfig,
  updateConfig,
  fetchCostSummary,
  fetchPnLHistory,
  fetchPerformanceByCategory,
} from "@/lib/api";
import type {
  PerformanceStats,
  CalibrationBucket,
  HealthStatus,
  AppConfig,
  CostSummary,
  PnLTimeSeriesResponse,
  CategoryPerformance,
} from "@/lib/types";

export function usePerformance(dateRange?: { from_date?: string; to_date?: string }) {
  const key = dateRange?.from_date
    ? `/api/performance?from=${dateRange.from_date}&to=${dateRange.to_date ?? ""}`
    : "/api/performance";
  const { data, error, isLoading } = useSWR<PerformanceStats>(
    key,
    () => fetchPerformance(dateRange)
  );
  return { data, error, isLoading };
}

export function useCalibration(dateRange?: { from_date?: string; to_date?: string }) {
  const key = dateRange?.from_date
    ? `/api/performance/calibration?from=${dateRange.from_date}&to=${dateRange.to_date ?? ""}`
    : "/api/performance/calibration";
  const { data, error, isLoading } = useSWR<CalibrationBucket[]>(
    key,
    () => fetchCalibration(dateRange)
  );
  return { data, error, isLoading };
}

export function useHealth() {
  const { data, error, isLoading, mutate } = useSWR<HealthStatus>(
    "/api/health",
    () => fetchHealth(),
    { refreshInterval: 30000 }
  );
  return { data, error, isLoading, mutate };
}

export function useConfig() {
  const { data, error, isLoading, mutate } = useSWR<AppConfig>(
    "/api/config",
    () => fetchConfig()
  );
  return { data, error, isLoading, mutate };
}

export function useUpdateConfig() {
  const { trigger, isMutating } = useSWRMutation(
    "/api/config",
    (_key: string, { arg }: { arg: Partial<AppConfig> }) => updateConfig(arg)
  );
  return { trigger, isUpdating: isMutating };
}

export function useCostSummary() {
  const { data, error, isLoading } = useSWR<CostSummary>(
    "/api/performance/costs",
    () => fetchCostSummary()
  );
  return { data, error, isLoading };
}

export function usePnLHistory(dateRange?: { from_date?: string; to_date?: string }) {
  const key = dateRange?.from_date
    ? `/api/performance/pnl-history?from=${dateRange.from_date}&to=${dateRange.to_date ?? ""}`
    : "/api/performance/pnl-history";
  const { data, error, isLoading } = useSWR<PnLTimeSeriesResponse>(
    key,
    () => fetchPnLHistory(dateRange)
  );
  return { data, error, isLoading };
}

export function usePerformanceByCategory() {
  const { data, error, isLoading } = useSWR<CategoryPerformance[]>(
    "/api/performance/by-category",
    () => fetchPerformanceByCategory()
  );
  return { data, error, isLoading };
}
