"use client";

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import {
  fetchPerformance,
  fetchCalibration,
  fetchHealth,
  fetchConfig,
  updateConfig,
} from "@/lib/api";
import type {
  PerformanceStats,
  CalibrationBucket,
  HealthStatus,
  AppConfig,
} from "@/lib/types";

export function usePerformance() {
  const { data, error, isLoading } = useSWR<PerformanceStats>(
    "/api/performance",
    () => fetchPerformance()
  );
  return { data, error, isLoading };
}

export function useCalibration() {
  const { data, error, isLoading } = useSWR<CalibrationBucket[]>(
    "/api/performance/calibration",
    () => fetchCalibration()
  );
  return { data, error, isLoading };
}

export function useHealth() {
  const { data, error, isLoading } = useSWR<HealthStatus>(
    "/api/health",
    () => fetchHealth(),
    { refreshInterval: 30000 }
  );
  return { data, error, isLoading };
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
