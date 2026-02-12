"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/empty-state";
import { CardSkeleton } from "@/components/shared/loading-skeleton";
import { usePerformanceByCategory } from "@/hooks/use-performance";
import { EMPTY_STATES } from "@/lib/constants";

interface CategoryData {
  category: string;
  accuracy: number;
  count: number;
}

function CategoryTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: CategoryData }>;
}) {
  if (!active || !payload?.length) return null;
  const item = payload[0].payload;

  return (
    <div className="rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm shadow-md">
      <p className="font-medium">{item.category}</p>
      <p className="text-foreground-muted">
        Accuracy: {(item.accuracy * 100).toFixed(1)}%
      </p>
      <p className="text-foreground-muted">{item.count} markets</p>
    </div>
  );
}

export function AccuracyByCategory() {
  const { data: categories, isLoading } = usePerformanceByCategory();

  if (isLoading) {
    return <CardSkeleton />;
  }

  const chartData: CategoryData[] = (categories ?? []).map((c) => ({
    category: c.category || "Unknown",
    accuracy: c.hit_rate,
    count: c.total_resolved,
  }));

  if (chartData.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Accuracy by Sport</CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState
            title="No category data"
            description={EMPTY_STATES.performance}
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Accuracy by Sport</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={chartData}
              layout="vertical"
              margin={{ top: 5, right: 20, bottom: 5, left: 80 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="var(--border)"
                opacity={0.5}
                horizontal={false}
              />
              <XAxis
                type="number"
                domain={[0, 1]}
                tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
                stroke="var(--foreground-subtle)"
                fontSize={11}
              />
              <YAxis
                type="category"
                dataKey="category"
                stroke="var(--foreground-subtle)"
                fontSize={11}
                width={75}
              />
              <Tooltip content={<CategoryTooltip />} cursor={false} />
              <Bar
                dataKey="accuracy"
                fill="var(--primary)"
                radius={[0, 4, 4, 0]}
                barSize={20}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
