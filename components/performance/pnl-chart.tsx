"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/empty-state";
import { CardSkeleton } from "@/components/shared/loading-skeleton";
import { usePerformance } from "@/hooks/use-performance";
import { formatCurrency } from "@/lib/utils";
import { EMPTY_STATES } from "@/lib/constants";

function PnlTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ value: number }>;
}) {
  if (!active || !payload?.length) return null;
  const value = payload[0].value;

  return (
    <div className="rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm shadow-md">
      <p
        className="font-semibold tabular-nums"
        style={{
          color: value >= 0 ? "var(--ev-positive)" : "var(--ev-negative)",
        }}
      >
        {value >= 0 ? "+" : ""}
        {formatCurrency(value)}
      </p>
    </div>
  );
}

export function PnlChart({
  dateRange,
}: {
  dateRange?: { from_date?: string; to_date?: string };
}) {
  const { data, isLoading } = usePerformance(dateRange);

  if (isLoading) {
    return <CardSkeleton />;
  }

  const totalPnl = data?.total_pnl ?? 0;

  // For now, show a single-point summary since we don't have time-series P&L data
  // from the API. The full time-series would need a dedicated endpoint.
  const chartData = [
    { label: "Start", pnl: 0 },
    { label: "Current", pnl: totalPnl },
  ];

  const isPositive = totalPnl >= 0;

  if (data?.total_resolved === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Cumulative P&L</CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState
            title="No P&L data"
            description={EMPTY_STATES.performance}
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Cumulative P&L</CardTitle>
        <p
          className="text-2xl font-semibold tabular-nums"
          style={{
            color: isPositive ? "var(--ev-positive)" : "var(--ev-negative)",
          }}
        >
          {isPositive ? "+" : ""}
          {formatCurrency(totalPnl)}
        </p>
      </CardHeader>
      <CardContent>
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={chartData}
              margin={{ top: 5, right: 10, bottom: 5, left: 10 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="var(--border)"
                opacity={0.5}
              />
              <XAxis
                dataKey="label"
                stroke="var(--foreground-subtle)"
                fontSize={11}
              />
              <YAxis
                tickFormatter={(v: number) => `$${v}`}
                stroke="var(--foreground-subtle)"
                fontSize={11}
              />
              <Tooltip content={<PnlTooltip />} cursor={false} />
              <defs>
                <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop
                    offset="5%"
                    stopColor={
                      isPositive ? "var(--ev-positive)" : "var(--ev-negative)"
                    }
                    stopOpacity={0.3}
                  />
                  <stop
                    offset="95%"
                    stopColor={
                      isPositive ? "var(--ev-positive)" : "var(--ev-negative)"
                    }
                    stopOpacity={0}
                  />
                </linearGradient>
              </defs>
              <Area
                type="monotone"
                dataKey="pnl"
                stroke={
                  isPositive ? "var(--ev-positive)" : "var(--ev-negative)"
                }
                fill="url(#pnlGradient)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
