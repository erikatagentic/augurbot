"use client";

import { CheckCircle, XCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/empty-state";
import { CardSkeleton } from "@/components/shared/loading-skeleton";
import { useRecommendationsHistory } from "@/hooks/use-recommendations";
import { formatCurrency, truncateText, formatRelativeTime } from "@/lib/utils";
import { EMPTY_STATES } from "@/lib/constants";

export function RecentResolutions() {
  const { data, isLoading } = useRecommendationsHistory();

  if (isLoading) {
    return (
      <section>
        <h2 className="mb-4 text-lg font-medium">Recent Resolutions</h2>
        <CardSkeleton />
      </section>
    );
  }

  const recommendations = data?.recommendations?.slice(0, 10) ?? [];
  const markets = data?.markets ?? {};

  if (recommendations.length === 0) {
    return (
      <section>
        <h2 className="mb-4 text-lg font-medium">Recent Resolutions</h2>
        <EmptyState
          title="No resolutions yet"
          description={EMPTY_STATES.performance}
        />
      </section>
    );
  }

  return (
    <section>
      <h2 className="mb-4 text-lg font-medium">Recent Resolutions</h2>
      <Card>
        <CardContent>
          <div className="divide-y divide-border">
            {recommendations.map((rec) => {
              const market = markets[rec.market_id];
              const question = market?.question ?? "Unknown market";
              const outcome = market?.outcome;
              const isWin =
                outcome !== null &&
                outcome !== undefined &&
                ((rec.direction === "yes" && outcome === true) ||
                  (rec.direction === "no" && outcome === false));

              return (
                <div
                  key={rec.id}
                  className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    {isWin ? (
                      <CheckCircle
                        className="h-5 w-5 shrink-0"
                        style={{ color: "var(--ev-positive)" }}
                      />
                    ) : (
                      <XCircle
                        className="h-5 w-5 shrink-0"
                        style={{ color: "var(--ev-negative)" }}
                      />
                    )}
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">
                        {truncateText(question, 80)}
                      </p>
                      <p className="text-xs text-foreground-muted">
                        {formatRelativeTime(rec.created_at)}
                      </p>
                    </div>
                  </div>
                  <span
                    className="shrink-0 text-sm font-semibold tabular-nums"
                    style={{
                      color: isWin
                        ? "var(--ev-positive)"
                        : "var(--ev-negative)",
                    }}
                  >
                    {isWin ? "+" : "-"}
                    {formatCurrency(Math.abs(rec.ev * 100))}
                  </span>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
