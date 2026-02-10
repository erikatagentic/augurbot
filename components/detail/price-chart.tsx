"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Scatter,
  ComposedChart,
  ReferenceLine,
} from "recharts";

import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import type { ChartConfig } from "@/components/ui/chart";
import type { MarketSnapshot, AIEstimate } from "@/lib/types";

const chartConfig = {
  marketPrice: {
    label: "Market Price",
    color: "var(--primary)",
  },
  aiEstimate: {
    label: "AI Estimate",
    color: "var(--ev-positive)",
  },
} satisfies ChartConfig;

interface ChartDataPoint {
  timestamp: number;
  date: string;
  marketPrice: number | null;
  aiEstimate: number | null;
}

function buildChartData(
  snapshots: MarketSnapshot[],
  estimates: AIEstimate[]
): ChartDataPoint[] {
  const pointMap = new Map<number, ChartDataPoint>();

  for (const snap of snapshots) {
    const ts = new Date(snap.captured_at).getTime();
    const dateStr = new Date(snap.captured_at).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
    pointMap.set(ts, {
      timestamp: ts,
      date: dateStr,
      marketPrice: snap.price_yes,
      aiEstimate: null,
    });
  }

  for (const est of estimates) {
    const ts = new Date(est.created_at).getTime();
    const dateStr = new Date(est.created_at).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
    const existing = pointMap.get(ts);
    if (existing) {
      existing.aiEstimate = est.probability;
    } else {
      pointMap.set(ts, {
        timestamp: ts,
        date: dateStr,
        marketPrice: null,
        aiEstimate: est.probability,
      });
    }
  }

  return Array.from(pointMap.values()).sort(
    (a, b) => a.timestamp - b.timestamp
  );
}

export function PriceChart({
  snapshots,
  estimates,
}: {
  snapshots: MarketSnapshot[];
  estimates: AIEstimate[];
}) {
  const data = buildChartData(snapshots, estimates);

  if (!data.length) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Price History</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-foreground-muted">
            No price data available yet.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Price History</CardTitle>
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig} className="h-[300px] w-full">
          <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11 }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              domain={[0, 1]}
              tick={{ fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(val: number) => `${(val * 100).toFixed(0)}%`}
            />
            <ChartTooltip
              content={
                <ChartTooltipContent
                  formatter={(value) => {
                    if (typeof value === "number") {
                      return `${(value * 100).toFixed(1)}%`;
                    }
                    return String(value);
                  }}
                />
              }
            />
            <ReferenceLine y={0.5} stroke="var(--border)" strokeDasharray="3 3" />
            <Area
              type="monotone"
              dataKey="marketPrice"
              stroke="var(--color-marketPrice)"
              fill="var(--color-marketPrice)"
              fillOpacity={0.1}
              strokeWidth={2}
              connectNulls
              dot={false}
            />
            <Scatter
              dataKey="aiEstimate"
              fill="var(--color-aiEstimate)"
              stroke="var(--color-aiEstimate)"
              strokeWidth={2}
              r={5}
              shape="diamond"
            />
          </ComposedChart>
        </ChartContainer>

        <div className="mt-4 flex items-center justify-center gap-6 text-xs text-foreground-muted">
          <div className="flex items-center gap-1.5">
            <div
              className="h-2 w-4 rounded-sm"
              style={{ backgroundColor: "var(--primary)" }}
            />
            <span>Market Price</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div
              className="h-3 w-3 rotate-45 rounded-sm"
              style={{ backgroundColor: "var(--ev-positive)" }}
            />
            <span>AI Estimate</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
