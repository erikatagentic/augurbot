"use client";

import { RefreshCw, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useHealth } from "@/hooks/use-performance";
import { useScanTrigger } from "@/hooks/use-recommendations";
import { formatRelativeTime } from "@/lib/utils";

export function ScanStatus() {
  const { data: health, isLoading: healthLoading } = useHealth();
  const { trigger, isScanning } = useScanTrigger();

  const isHealthy = health?.status === "ok" && health?.database_connected;
  const lastScan = health?.last_scan_at;

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
            <span>Last scan {formatRelativeTime(lastScan)}</span>
          ) : (
            <span>No scans yet</span>
          )}
        </div>
      )}
      <Button
        variant="outline"
        size="sm"
        onClick={async () => {
          try {
            await trigger();
            toast.success("Scan started");
          } catch {
            toast.error("Failed to start scan");
          }
        }}
        disabled={isScanning}
      >
        {isScanning ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <RefreshCw className="h-4 w-4" />
        )}
        {isScanning ? "Scanning..." : "Scan Now"}
      </Button>
    </div>
  );
}
