"use client";

import { useState, useMemo } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Sidebar } from "@/components/layout/sidebar";
import { PageContainer } from "@/components/layout/page-container";
import { Header } from "@/components/layout/header";
import { CalibrationChart } from "@/components/performance/calibration-chart";
import { BrierScoreCard } from "@/components/performance/brier-score-card";
import { PnlChart } from "@/components/performance/pnl-chart";
import { AccuracyByCategory } from "@/components/performance/accuracy-by-category";
import { AIvsActualComparison } from "@/components/performance/ai-vs-actual";
import { Skeleton } from "@/components/shared/loading-skeleton";
import { usePerformance } from "@/hooks/use-performance";
import { formatPercent, formatCurrency } from "@/lib/utils";
import { PAGE_TITLES } from "@/lib/constants";
import { cn } from "@/lib/utils";

type DateRangeKey = "7d" | "30d" | "90d" | "all";

const DATE_RANGE_OPTIONS: { key: DateRangeKey; label: string }[] = [
  { key: "7d", label: "7 Days" },
  { key: "30d", label: "30 Days" },
  { key: "90d", label: "90 Days" },
  { key: "all", label: "All Time" },
];

function getDateRange(key: DateRangeKey): { from_date?: string; to_date?: string } | undefined {
  if (key === "all") return undefined;
  const now = new Date();
  const days = key === "7d" ? 7 : key === "30d" ? 30 : 90;
  const from = new Date(now.getTime() - days * 24 * 60 * 60 * 1000);
  return { from_date: from.toISOString() };
}

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <p className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
          {label}
        </p>
        <p
          className="mt-2 text-2xl font-semibold tabular-nums"
          style={color ? { color } : undefined}
        >
          {value}
        </p>
      </CardContent>
    </Card>
  );
}

function StatsGrid({
  dateRange,
}: {
  dateRange?: { from_date?: string; to_date?: string };
}) {
  const { data, isLoading } = usePerformance(dateRange);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="pt-6">
                <Skeleton className="h-4 w-20 mb-3" />
                <Skeleton className="h-8 w-16" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  const trading = data?.trading ?? {
    total_resolved: 0,
    hit_rate: 0,
    total_simulated_pnl: 0,
    avg_edge: 0,
    avg_brier_score: 0,
    total_pnl: 0,
  };
  const forecasting = data?.forecasting ?? {
    total_resolved: 0,
    hit_rate: 0,
    avg_brier_score: 0,
    total_simulated_pnl: 0,
    avg_edge: 0,
    total_pnl: 0,
  };

  return (
    <div className="space-y-6">
      {/* Trading Performance — only recommended markets */}
      <div>
        <p className="mb-3 text-xs font-medium uppercase tracking-widest text-foreground-muted">
          Trading Performance
          <span className="ml-2 text-foreground-subtle font-normal normal-case tracking-normal">
            (recommended markets only)
          </span>
        </p>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Recommended" value={String(trading.total_resolved)} />
          <StatCard
            label="Hit Rate"
            value={trading.total_resolved > 0 ? formatPercent(trading.hit_rate) : "--"}
            color={trading.total_resolved > 0 ? (trading.hit_rate > 0.5 ? "var(--ev-positive)" : "var(--ev-negative)") : undefined}
          />
          <StatCard
            label="Simulated P&L"
            value={trading.total_resolved > 0 ? `${trading.total_simulated_pnl >= 0 ? "+" : ""}${formatCurrency(trading.total_simulated_pnl)}` : "--"}
            color={trading.total_resolved > 0 ? (trading.total_simulated_pnl >= 0 ? "var(--ev-positive)" : "var(--ev-negative)") : undefined}
          />
          <StatCard
            label="Avg Edge"
            value={trading.total_resolved > 0 ? formatPercent(trading.avg_edge) : "--"}
            color={trading.total_resolved > 0 ? (trading.avg_edge > 0.05 ? "var(--ev-positive)" : "var(--foreground)") : undefined}
          />
        </div>
      </div>

      {/* Forecasting Accuracy — all estimated markets */}
      <div>
        <p className="mb-3 text-xs font-medium uppercase tracking-widest text-foreground-muted">
          Forecasting Accuracy
          <span className="ml-2 text-foreground-subtle font-normal normal-case tracking-normal">
            (all estimated markets)
          </span>
        </p>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Markets Estimated" value={String(forecasting.total_resolved)} />
          <StatCard
            label="Hit Rate"
            value={forecasting.total_resolved > 0 ? formatPercent(forecasting.hit_rate) : "--"}
            color={forecasting.total_resolved > 0 ? (forecasting.hit_rate > 0.5 ? "var(--ev-positive)" : "var(--ev-negative)") : undefined}
          />
          <StatCard
            label="Avg Brier Score"
            value={forecasting.total_resolved > 0 ? forecasting.avg_brier_score.toFixed(4) : "--"}
          />
          <StatCard
            label="Avg Edge"
            value={forecasting.total_resolved > 0 ? formatPercent(forecasting.avg_edge) : "--"}
          />
        </div>
      </div>
    </div>
  );
}

export default function PerformancePage() {
  const [rangeKey, setRangeKey] = useState<DateRangeKey>("all");
  const dateRange = useMemo(() => getDateRange(rangeKey), [rangeKey]);

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 overflow-auto">
        <PageContainer>
          <Header
            title={PAGE_TITLES.performance}
            actions={
              <div className="flex gap-1 rounded-lg bg-surface p-1">
                {DATE_RANGE_OPTIONS.map((opt) => (
                  <Button
                    key={opt.key}
                    variant="ghost"
                    size="sm"
                    className={cn(
                      "h-7 px-3 text-xs",
                      rangeKey === opt.key &&
                        "bg-surface-raised text-foreground"
                    )}
                    onClick={() => setRangeKey(opt.key)}
                  >
                    {opt.label}
                  </Button>
                ))}
              </div>
            }
          />
          <div className="space-y-8">
            <StatsGrid dateRange={dateRange} />
            <CalibrationChart dateRange={dateRange} />
            <div className="grid gap-6 lg:grid-cols-2">
              <BrierScoreCard dateRange={dateRange} />
              <PnlChart dateRange={dateRange} />
            </div>
            <AccuracyByCategory dateRange={dateRange} />
            <AIvsActualComparison />
          </div>
        </PageContainer>
      </main>
    </div>
  );
}
