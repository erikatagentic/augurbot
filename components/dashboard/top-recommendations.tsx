"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowUpRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EVBadge } from "@/components/shared/ev-badge";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { ConfidenceBadge } from "@/components/shared/confidence-badge";
import { EmptyState } from "@/components/shared/empty-state";
import { CardSkeleton } from "@/components/shared/loading-skeleton";
import { useRecommendations } from "@/hooks/use-recommendations";
import { TradeLogDialog } from "@/components/trades/trade-log-dialog";
import { staggerContainer, fadeInUp } from "@/lib/motion";
import { formatPercent, truncateText } from "@/lib/utils";
import { EMPTY_STATES } from "@/lib/constants";

import type { Recommendation, Market, Confidence } from "@/lib/types";

function RecommendationCard({
  rec,
  market,
}: {
  rec: Recommendation;
  market: Market | undefined;
}) {
  const question = market?.question ?? "Unknown market";
  const platform = market?.platform ?? "polymarket";
  const confidence = (market ? "medium" : "medium") as Confidence;

  return (
    <motion.div variants={fadeInUp}>
      <Link href={`/markets/${rec.market_id}`} className="block">
        <Card className="transition-colors hover:border-border-hover">
          <CardContent className="space-y-4">
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm font-medium leading-snug">
                {truncateText(question, 100)}
              </p>
              <ArrowUpRight className="h-4 w-4 shrink-0 text-foreground-muted" />
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <PlatformBadge platform={platform} />
              <Badge
                variant="outline"
                className="text-xs px-2 py-0.5 font-medium"
                style={{
                  borderColor:
                    rec.direction === "yes"
                      ? "var(--ev-positive)"
                      : "var(--ev-negative)",
                  color:
                    rec.direction === "yes"
                      ? "var(--ev-positive)"
                      : "var(--ev-negative)",
                }}
              >
                {rec.direction.toUpperCase()}
              </Badge>
              <EVBadge ev={rec.ev} size="sm" />
              <ConfidenceBadge confidence={confidence} />
            </div>

            <div className="grid grid-cols-3 gap-4 rounded-lg bg-surface-raised p-3">
              <div>
                <p className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
                  Market
                </p>
                <p className="mt-1 text-lg font-semibold tabular-nums">
                  {formatPercent(rec.market_price)}
                </p>
              </div>
              <div>
                <p className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
                  AI Est.
                </p>
                <p className="mt-1 text-lg font-semibold tabular-nums">
                  {formatPercent(rec.ai_probability)}
                </p>
              </div>
              <div>
                <p className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
                  Edge
                </p>
                <p
                  className="mt-1 text-lg font-semibold tabular-nums"
                  style={{
                    color:
                      rec.edge > 0.1
                        ? "var(--ev-positive)"
                        : rec.edge > 0.05
                          ? "var(--ev-moderate)"
                          : "var(--foreground)",
                  }}
                >
                  {formatPercent(rec.edge)}
                </p>
              </div>
            </div>

            <div className="flex items-center justify-between text-xs text-foreground-muted">
              <span>
                Kelly: {formatPercent(rec.kelly_fraction)}
              </span>
              <div onClick={(e) => e.preventDefault()}>
                <TradeLogDialog recommendation={rec} market={market} />
              </div>
            </div>
          </CardContent>
        </Card>
      </Link>
    </motion.div>
  );
}

export function TopRecommendations() {
  const { data, isLoading } = useRecommendations();

  if (isLoading) {
    return (
      <section>
        <h2 className="mb-4 text-lg font-medium">Top Recommendations</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      </section>
    );
  }

  const recommendations = data?.recommendations?.slice(0, 5) ?? [];
  const markets = data?.markets ?? {};

  if (recommendations.length === 0) {
    return (
      <section>
        <h2 className="mb-4 text-lg font-medium">Top Recommendations</h2>
        <EmptyState
          title="No recommendations"
          description={EMPTY_STATES.recommendations}
        />
      </section>
    );
  }

  return (
    <section>
      <h2 className="mb-4 text-lg font-medium">Top Recommendations</h2>
      <motion.div
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
        variants={staggerContainer}
        initial="initial"
        animate="animate"
      >
        {recommendations.map((rec) => (
          <RecommendationCard
            key={rec.id}
            rec={rec}
            market={markets[rec.market_id]}
          />
        ))}
      </motion.div>
    </section>
  );
}
