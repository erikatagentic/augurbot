"use client";

import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/empty-state";
import { CardSkeleton } from "@/components/shared/loading-skeleton";
import { useCalibration } from "@/hooks/use-performance";
import { EMPTY_STATES } from "@/lib/constants";

import type { CalibrationBucket } from "@/lib/types";

function CalibrationTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: CalibrationBucket }>;
}) {
  if (!active || !payload?.length) return null;
  const bucket = payload[0].payload;

  return (
    <div className="rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm shadow-md">
      <p className="font-medium">
        {(bucket.bucket_min * 100).toFixed(0)}%&ndash;
        {(bucket.bucket_max * 100).toFixed(0)}%
      </p>
      <p className="text-foreground-muted">
        Predicted avg: {(bucket.predicted_avg * 100).toFixed(1)}%
      </p>
      <p className="text-foreground-muted">
        Actual freq: {(bucket.actual_frequency * 100).toFixed(1)}%
      </p>
      <p className="text-foreground-muted">{bucket.count} forecasts</p>
    </div>
  );
}

export function CalibrationChart() {
  const { data: buckets, isLoading } = useCalibration();

  if (isLoading) {
    return <CardSkeleton />;
  }

  if (!buckets || buckets.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Calibration</CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState
            title="No calibration data"
            description={EMPTY_STATES.performance}
          />
        </CardContent>
      </Card>
    );
  }

  const diagonalPoints = Array.from({ length: 11 }, (_, i) => ({
    x: i * 0.1,
    y: i * 0.1,
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Calibration Curve</CardTitle>
        <p className="text-sm text-foreground-muted">
          When the AI says 70%, events should resolve YES ~70% of the time.
          Points on the diagonal line indicate perfect calibration.
        </p>
      </CardHeader>
      <CardContent>
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 10, right: 20, bottom: 20, left: 20 }}>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="var(--border)"
                opacity={0.5}
              />
              <XAxis
                type="number"
                dataKey="predicted_avg"
                domain={[0, 1]}
                tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
                label={{
                  value: "Predicted Probability",
                  position: "insideBottom",
                  offset: -10,
                  style: { fill: "var(--foreground-muted)", fontSize: 12 },
                }}
                stroke="var(--foreground-subtle)"
                fontSize={11}
              />
              <YAxis
                type="number"
                dataKey="actual_frequency"
                domain={[0, 1]}
                tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
                label={{
                  value: "Actual Frequency",
                  angle: -90,
                  position: "insideLeft",
                  offset: 0,
                  style: { fill: "var(--foreground-muted)", fontSize: 12 },
                }}
                stroke="var(--foreground-subtle)"
                fontSize={11}
              />
              <Tooltip
                content={<CalibrationTooltip />}
                cursor={false}
              />
              <ReferenceLine
                segment={[
                  { x: 0, y: 0 },
                  { x: 1, y: 1 },
                ]}
                stroke="var(--foreground-subtle)"
                strokeDasharray="6 4"
                strokeOpacity={0.6}
              />
              <Scatter
                data={buckets}
                fill="var(--primary)"
                stroke="var(--primary)"
                strokeWidth={2}
                r={6}
              />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
