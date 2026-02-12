"use client";

import { Clock, Search, Brain, TrendingUp } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { useLastScanSummary } from "@/hooks/use-recommendations";
import { formatDuration } from "@/lib/utils";

export function LastScanSummary() {
  const { data, isLoading } = useLastScanSummary();

  if (isLoading || !data || !data.completed_at) {
    return null;
  }

  const completedDate = new Date(data.completed_at);
  const timeLabel = completedDate.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between mb-3">
          <p className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
            Last Scan Summary
          </p>
          <span className="text-xs text-foreground-subtle">{timeLabel}</span>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="flex items-center gap-2">
            <Search className="h-4 w-4 text-foreground-subtle" />
            <div>
              <p className="text-lg font-semibold tabular-nums">{data.markets_found}</p>
              <p className="text-xs text-foreground-muted">Markets found</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Brain className="h-4 w-4 text-foreground-subtle" />
            <div>
              <p className="text-lg font-semibold tabular-nums">{data.markets_researched}</p>
              <p className="text-xs text-foreground-muted">Researched</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4" style={{ color: "var(--ev-positive)" }} />
            <div>
              <p className="text-lg font-semibold tabular-nums">{data.recommendations_created}</p>
              <p className="text-xs text-foreground-muted">Recommendations</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-foreground-subtle" />
            <div>
              <p className="text-lg font-semibold tabular-nums">
                {formatDuration(data.duration_seconds)}
              </p>
              <p className="text-xs text-foreground-muted">Duration</p>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
