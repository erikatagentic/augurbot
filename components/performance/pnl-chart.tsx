"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/empty-state";
import { CardSkeleton } from "@/components/shared/loading-skeleton";
import { usePnLHistory } from "@/hooks/use-performance";
import { formatCurrency } from "@/lib/utils";
import { EMPTY_STATES } from "@/lib/constants";

function PnlTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value: number; dataKey: string; color: string; name: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;

  return (
    <div className="rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm shadow-md">
      {label && <p className="text-xs text-foreground-muted mb-1">{label}</p>}
      {payload.map((p) => (
        <p
          key={p.dataKey}
          className="font-semibold tabular-nums"
          style={{ color: p.color }}
        >
          {p.name}: {p.value >= 0 ? "+" : ""}
          {formatCurrency(p.value)}
        </p>
      ))}
    </div>
  );
}

export function PnlChart({
  dateRange,
}: {
  dateRange?: { from_date?: string; to_date?: string };
}) {
  const { data, isLoading } = usePnLHistory(dateRange);

  if (isLoading) {
    return <CardSkeleton />;
  }

  const dataPoints = data?.data_points ?? [];

  if (dataPoints.length < 1) {
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

  const chartData = dataPoints.map((dp) => {
    const d = new Date(dp.resolved_at);
    return {
      date: `${d.toLocaleString("default", { month: "short" })} ${d.getDate()}`,
      actual: dp.cumulative_pnl,
      simulated: dp.cumulative_simulated_pnl,
    };
  });

  const latestActual = chartData[chartData.length - 1]?.actual ?? 0;
  const latestSim = chartData[chartData.length - 1]?.simulated ?? 0;
  const hasActualTrades = latestActual !== 0;
  const isSimPositive = latestSim >= 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Cumulative P&L</CardTitle>
        <div className="flex gap-6 mt-1">
          <div>
            <p className="text-xs text-foreground-muted">Simulated</p>
            <p
              className="text-2xl font-semibold tabular-nums"
              style={{ color: isSimPositive ? "var(--ev-positive)" : "var(--ev-negative)" }}
            >
              {latestSim >= 0 ? "+" : ""}
              {formatCurrency(latestSim)}
            </p>
          </div>
          {hasActualTrades && (
            <div>
              <p className="text-xs text-foreground-muted">Actual</p>
              <p
                className="text-2xl font-semibold tabular-nums"
                style={{
                  color: latestActual >= 0 ? "var(--ev-positive)" : "var(--ev-negative)",
                }}
              >
                {latestActual >= 0 ? "+" : ""}
                {formatCurrency(latestActual)}
              </p>
            </div>
          )}
        </div>
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
                dataKey="date"
                stroke="var(--foreground-subtle)"
                fontSize={11}
              />
              <YAxis
                tickFormatter={(v: number) => `$${v}`}
                stroke="var(--foreground-subtle)"
                fontSize={11}
              />
              <Tooltip content={<PnlTooltip />} cursor={false} />
              <Legend
                verticalAlign="bottom"
                height={24}
                iconType="line"
                wrapperStyle={{ fontSize: 11, color: "var(--foreground-muted)" }}
              />
              <defs>
                <linearGradient id="simGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop
                    offset="5%"
                    stopColor="var(--primary)"
                    stopOpacity={0.2}
                  />
                  <stop
                    offset="95%"
                    stopColor="var(--primary)"
                    stopOpacity={0}
                  />
                </linearGradient>
              </defs>
              <Area
                type="monotone"
                dataKey="simulated"
                name="Simulated"
                stroke="var(--primary)"
                fill="url(#simGradient)"
                strokeWidth={2}
              />
              {hasActualTrades && (
                <Area
                  type="monotone"
                  dataKey="actual"
                  name="Actual"
                  stroke="var(--ev-positive)"
                  fill="none"
                  strokeWidth={2}
                  strokeDasharray="5 3"
                />
              )}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
