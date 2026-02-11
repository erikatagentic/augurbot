"use client";

import { useState, useEffect, useCallback } from "react";
import { RefreshCw, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useHealth } from "@/hooks/use-performance";
import { useScanTrigger } from "@/hooks/use-recommendations";
import { formatRelativeTime } from "@/lib/utils";

export function ScanStatus() {
  const { data: health, isLoading: healthLoading, mutate: refreshHealth } = useHealth();
  const { trigger, isScanning } = useScanTrigger();
  const [scanActive, setScanActive] = useState(false);

  const isHealthy = health?.status === "ok" && health?.database_connected;
  const lastScan = health?.last_scan_at;
  const showScanning = isScanning || scanActive;

  // Keep "Scanning..." visible for 30s after trigger, then refresh health
  useEffect(() => {
    if (!scanActive) return;
    const timer = setTimeout(() => {
      setScanActive(false);
      refreshHealth();
    }, 30_000);
    return () => clearTimeout(timer);
  }, [scanActive, refreshHealth]);

  const handleScan = useCallback(async () => {
    try {
      await trigger();
      setScanActive(true);
      toast.success(
        "Scan started — scanning Kalshi sports markets. This takes 2-3 minutes.",
        { duration: 6000 }
      );
    } catch {
      toast.error("Failed to start scan");
    }
  }, [trigger]);

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
          {showScanning ? (
            <span>Scanning Kalshi markets...</span>
          ) : lastScan ? (
            <span>Last scan {formatRelativeTime(lastScan)}</span>
          ) : (
            <span>No scans yet</span>
          )}
        </div>
      )}
      <Button
        variant="outline"
        size="sm"
        onClick={handleScan}
        disabled={showScanning}
      >
        {showScanning ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <RefreshCw className="h-4 w-4" />
        )}
        {showScanning ? "Scanning..." : "Scan Now"}
      </Button>
    </div>
  );
}
