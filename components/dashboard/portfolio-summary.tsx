"use client";

import { TrendingUp, Target, DollarSign, Activity } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/shared/loading-skeleton";
import { useRecommendations } from "@/hooks/use-recommendations";
import { usePerformance } from "@/hooks/use-performance";
import { formatPercent, formatCurrency } from "@/lib/utils";

import type { LucideIcon } from "lucide-react";

interface StatCardProps {
  label: string;
  value: string;
  icon: LucideIcon;
  color: string;
  isLoading: boolean;
}

function StatCard({ label, value, icon: Icon, color, isLoading }: StatCardProps) {
  return (
    <Card>
      <CardContent className="flex items-start justify-between">
        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
            {label}
          </p>
          {isLoading ? (
            <Skeleton className="h-10 w-24" />
          ) : (
            <p className="text-4xl font-[family-name:var(--font-display)] italic tabular-nums">
              {value}
            </p>
          )}
        </div>
        <div
          className="flex h-10 w-10 items-center justify-center rounded-lg"
          style={{ backgroundColor: `color-mix(in srgb, ${color} 15%, transparent)` }}
        >
          <Icon className="h-5 w-5" style={{ color }} />
        </div>
      </CardContent>
    </Card>
  );
}

export function PortfolioSummary() {
  const { data: recData, isLoading: recLoading } = useRecommendations();
  const { data: perfData, isLoading: perfLoading } = usePerformance();

  const activeCount = recData?.recommendations?.length ?? 0;
  const hitRate = perfData?.hit_rate ?? 0;
  const totalPnl = perfData?.total_pnl ?? 0;
  const avgBrier = perfData?.avg_brier_score ?? 0;

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard
        label="Active Recommendations"
        value={String(activeCount)}
        icon={TrendingUp}
        color="var(--ev-positive)"
        isLoading={recLoading}
      />
      <StatCard
        label="Win Rate"
        value={formatPercent(hitRate)}
        icon={Target}
        color="var(--platform-kalshi)"
        isLoading={perfLoading}
      />
      <StatCard
        label="Total P&L"
        value={formatCurrency(totalPnl)}
        icon={DollarSign}
        color={totalPnl >= 0 ? "var(--ev-positive)" : "var(--ev-negative)"}
        isLoading={perfLoading}
      />
      <StatCard
        label="Avg Brier Score"
        value={avgBrier.toFixed(3)}
        icon={Activity}
        color="var(--platform-polymarket)"
        isLoading={perfLoading}
      />
    </div>
  );
}
