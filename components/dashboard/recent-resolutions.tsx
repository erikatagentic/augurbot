"use client";

import { CheckCircle, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/empty-state";
import { CardSkeleton } from "@/components/shared/loading-skeleton";
import { useRecommendationsHistory } from "@/hooks/use-recommendations";
import { truncateText, formatRelativeTime, formatPercent } from "@/lib/utils";
import { EMPTY_STATES } from "@/lib/constants";

export function RecentResolutions() {
  const { data, isLoading } = useRecommendationsHistory();

  if (isLoading) {
    return (
      <section>
        <h2 className="mb-4 text-lg font-medium">Recent Results</h2>
        <CardSkeleton />
      </section>
    );
  }

  const allRecs = data?.recommendations ?? [];
  const markets = data?.markets ?? {};

  // Only show recommendations where the market has actually resolved
  const recommendations = allRecs
    .filter((rec) => {
      const market = markets[rec.market_id];
      return market?.outcome !== null && market?.outcome !== undefined;
    })
    .slice(0, 10);

  if (recommendations.length === 0) {
    return (
      <section>
        <h2 className="mb-4 text-lg font-medium">Recent Results</h2>
        <EmptyState
          title="No results yet"
          description={EMPTY_STATES.performance}
        />
      </section>
    );
  }

  return (
    <section>
      <h2 className="mb-4 text-lg font-medium">Recent Results</h2>
      <Card>
        <CardContent>
          <div className="divide-y divide-border">
            {recommendations.map((rec) => {
              const market = markets[rec.market_id];
              const question = market?.question ?? "Unknown market";
              const outcome = market?.outcome;
              const isCorrect =
                (rec.direction === "yes" && outcome === true) ||
                (rec.direction === "no" && outcome === false);

              return (
                <div
                  key={rec.id}
                  className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    {isCorrect ? (
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
                        AI: {formatPercent(rec.ai_probability)}{" "}
                        {rec.direction.toUpperCase()} | Result:{" "}
                        {outcome ? "YES" : "NO"}
                        <span className="ml-2">
                          {formatRelativeTime(rec.created_at)}
                        </span>
                      </p>
                    </div>
                  </div>
                  <Badge
                    variant="outline"
                    className="shrink-0 text-xs font-semibold"
                    style={{
                      borderColor: isCorrect
                        ? "var(--ev-positive)"
                        : "var(--ev-negative)",
                      color: isCorrect
                        ? "var(--ev-positive)"
                        : "var(--ev-negative)",
                    }}
                  >
                    {isCorrect ? "Correct" : "Wrong"}
                  </Badge>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
