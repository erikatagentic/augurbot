"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { RefreshCw, Loader2, CheckCircle2, XCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useHealth } from "@/hooks/use-performance";
import { useScanTrigger, useScanProgress } from "@/hooks/use-recommendations";
import { formatRelativeTime, formatDuration } from "@/lib/utils";
import { ApiError } from "@/lib/api";

import type { ScanProgress } from "@/lib/types";

function ScanProgressPanel({ progress }: { progress: ScanProgress }) {
  const pct =
    progress.markets_total > 0
      ? Math.round(
          (progress.markets_processed / progress.markets_total) * 100
        )
      : 0;

  const elapsed =
    progress.elapsed_seconds != null
      ? formatDuration(progress.elapsed_seconds)
      : null;

  const eta =
    progress.estimated_remaining_seconds != null &&
    progress.markets_processed >= 3
      ? formatDuration(progress.estimated_remaining_seconds)
      : null;

  return (
    <div className="flex flex-col gap-1.5 min-w-[280px]">
      <div className="flex items-center justify-between text-xs">
        <span className="flex items-center gap-2 text-foreground-muted">
          <Loader2 className="h-3 w-3 animate-spin" style={{ color: "var(--primary)" }} />
          {progress.phase === "fetching"
            ? "Fetching Kalshi markets..."
            : "Researching markets..."}
        </span>
        {elapsed && (
          <span className="text-foreground-subtle tabular-nums">{elapsed}</span>
        )}
      </div>

      {progress.markets_total > 0 && (
        <>
          <div className="h-1.5 rounded-full bg-surface-raised overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-700 ease-out"
              style={{
                width: `${pct}%`,
                backgroundColor: "var(--primary)",
              }}
            />
          </div>

          <div className="flex items-center justify-between text-xs text-foreground-subtle">
            <span className="tabular-nums">
              {progress.markets_processed}/{progress.markets_total} markets
            </span>
            {eta && <span className="tabular-nums">~{eta} remaining</span>}
          </div>
        </>
      )}

      {progress.current_market && (
        <p className="text-xs text-foreground-muted truncate max-w-[320px]">
          Analyzing: {progress.current_market}
        </p>
      )}

      {progress.markets_processed > 0 && (
        <div className="flex gap-3 text-xs text-foreground-subtle">
          <span>{progress.markets_researched} researched</span>
          <span>{progress.markets_skipped} cached</span>
          {progress.recommendations_created > 0 && (
            <span style={{ color: "var(--ev-positive)" }}>
              {progress.recommendations_created} recommendations
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function ScanCompleteSummary({ progress }: { progress: ScanProgress }) {
  const duration =
    progress.elapsed_seconds != null
      ? formatDuration(progress.elapsed_seconds)
      : null;

  return (
    <div className="flex items-center gap-2 text-xs text-foreground-muted">
      <CheckCircle2 className="h-3.5 w-3.5" style={{ color: "var(--ev-positive)" }} />
      <span>
        Scan complete: {progress.markets_researched} researched,{" "}
        {progress.recommendations_created} recommendations
        {duration && ` (${duration})`}
      </span>
    </div>
  );
}

function ScanFailedSummary({
  progress,
  onRetry,
}: {
  progress: ScanProgress;
  onRetry: () => void;
}) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <XCircle className="h-3.5 w-3.5" style={{ color: "var(--ev-negative)" }} />
      <span className="text-foreground-muted">
        Scan failed{progress.error ? `: ${progress.error}` : ""}
      </span>
      <Button variant="outline" size="sm" onClick={onRetry} className="h-6 px-2 text-xs">
        Retry
      </Button>
    </div>
  );
}

export function ScanStatus() {
  const {
    data: health,
    isLoading: healthLoading,
    mutate: refreshHealth,
  } = useHealth();
  const { trigger } = useScanTrigger();
  const [scanActive, setScanActive] = useState(false);
  const { data: progress } = useScanProgress(scanActive);

  const isHealthy = health?.status === "ok" && health?.database_connected;
  const lastScan = health?.last_scan_at;
  const nextScanAt = health?.next_scan_at;

  // Compute "Next scan in Xh Ym" countdown
  const nextScanLabel = useMemo(() => {
    if (!nextScanAt) return null;
    const diff = new Date(nextScanAt).getTime() - Date.now();
    if (diff <= 0) return "soon";
    const hours = Math.floor(diff / 3_600_000);
    const minutes = Math.floor((diff % 3_600_000) / 60_000);
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
  }, [nextScanAt]);

  // Transition from complete/failed back to idle after 8 seconds
  useEffect(() => {
    if (
      !progress ||
      (progress.phase !== "complete" && progress.phase !== "failed")
    )
      return;

    const timer = setTimeout(() => {
      setScanActive(false);
      refreshHealth();
    }, 8000);
    return () => clearTimeout(timer);
  }, [progress?.phase, refreshHealth]);

  const handleScan = useCallback(async () => {
    try {
      await trigger();
      setScanActive(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast.error("A scan is already running");
        setScanActive(true);
      } else {
        toast.error("Failed to start scan");
      }
    }
  }, [trigger]);

  // Active scan with progress data
  if (scanActive && progress?.is_running) {
    return <ScanProgressPanel progress={progress} />;
  }

  // Scan just completed
  if (scanActive && progress?.phase === "complete") {
    return <ScanCompleteSummary progress={progress} />;
  }

  // Scan failed
  if (scanActive && progress?.phase === "failed") {
    return (
      <ScanFailedSummary progress={progress} onRetry={handleScan} />
    );
  }

  // Default idle state
  return (
    <div className="flex items-center gap-3">
      {!healthLoading && (
        <div className="flex items-center gap-2 text-xs text-foreground-muted">
          <span
            className="h-2 w-2 rounded-full"
            style={{
              backgroundColor: isHealthy
                ? "var(--ev-positive)"
                : "var(--ev-negative)",
            }}
          />
          {lastScan ? (
            <span>
              Last scan {formatRelativeTime(lastScan)}
              {nextScanLabel && <> &middot; Next in {nextScanLabel}</>}
            </span>
          ) : (
            <span>No scans yet</span>
          )}
        </div>
      )}
      <Button variant="outline" size="sm" onClick={handleScan}>
        <RefreshCw className="h-4 w-4" />
        Scan Now
      </Button>
    </div>
  );
}
