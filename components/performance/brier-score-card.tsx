"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/shared/loading-skeleton";
import { usePerformance } from "@/hooks/use-performance";

function getScoreInterpretation(score: number): {
  label: string;
  color: string;
} {
  if (score <= 0.1) return { label: "Excellent", color: "var(--ev-positive)" };
  if (score <= 0.15) return { label: "Good", color: "var(--ev-positive)" };
  if (score <= 0.2) return { label: "Fair", color: "var(--ev-moderate)" };
  if (score <= 0.25) return { label: "Below Average", color: "var(--ev-negative)" };
  return { label: "Poor", color: "var(--ev-negative)" };
}

export function BrierScoreCard() {
  const { data, isLoading } = usePerformance();

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Brier Score</CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-12 w-24" />
        </CardContent>
      </Card>
    );
  }

  const score = data?.avg_brier_score ?? 0;
  const interpretation = getScoreInterpretation(score);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Brier Score</CardTitle>
        <p className="text-sm text-foreground-muted">
          Lower is better. 0.0 = perfect, 0.25 = random chance.
        </p>
      </CardHeader>
      <CardContent>
        <p
          className="text-4xl font-display italic tabular-nums"
          style={{ color: interpretation.color }}
        >
          {score.toFixed(3)}
        </p>
        <p
          className="mt-1 text-sm font-medium"
          style={{ color: interpretation.color }}
        >
          {interpretation.label}
        </p>
      </CardContent>
    </Card>
  );
}
