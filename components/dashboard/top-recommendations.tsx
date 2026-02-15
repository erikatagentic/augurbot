"use client";

import { useState } from "react";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowUpRight, ExternalLink, Zap } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { EVBadge } from "@/components/shared/ev-badge";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { CategoryBadge } from "@/components/shared/category-badge";
import { ConfidenceBadge } from "@/components/shared/confidence-badge";
import { EmptyState } from "@/components/shared/empty-state";
import { CardSkeleton } from "@/components/shared/loading-skeleton";
import { useRecommendations } from "@/hooks/use-recommendations";
import { TradeLogDialog } from "@/components/trades/trade-log-dialog";
import { staggerContainer, fadeInUp } from "@/lib/motion";
import { formatPercent, truncateText, getKalshiMarketUrl } from "@/lib/utils";
import { executeTrade } from "@/lib/api";
import { useConfig } from "@/hooks/use-performance";
import { EMPTY_STATES } from "@/lib/constants";

import type { Recommendation, Market, Confidence } from "@/lib/types";

function PlaceBetDialog({
  rec,
  market,
}: {
  rec: Recommendation;
  market: Market | undefined;
}) {
  const [open, setOpen] = useState(false);
  const [isPlacing, setIsPlacing] = useState(false);
  const { data: config } = useConfig();

  const bankroll = config?.bankroll ?? 1000;
  const maxBetFrac = config?.max_single_bet_fraction ?? 0.05;
  const maxBet = bankroll * maxBetFrac;
  const kellyBet = rec.kelly_fraction * bankroll;
  const betAmount = Math.min(kellyBet, maxBet);
  const betLabel = market?.outcome_label
    ? `Bet: ${market.outcome_label}`
    : rec.direction.toUpperCase();

  async function handlePlace() {
    setIsPlacing(true);
    try {
      const result = await executeTrade(rec.id, betAmount);
      toast.success(
        `Bet placed! ${result.contracts} contracts at ${result.price_cents}¢ ($${result.total_cost.toFixed(2)})`
      );
      setOpen(false);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to place bet"
      );
    } finally {
      setIsPlacing(false);
    }
  }

  if (market?.platform !== "kalshi") return null;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
          }}
          className="flex items-center gap-1 text-xs font-medium hover:text-foreground transition-colors"
          style={{ color: "var(--ev-positive)" }}
        >
          <Zap className="h-3 w-3" />
          Place Bet
        </button>
      </DialogTrigger>
      <DialogContent onClick={(e) => e.stopPropagation()}>
        <DialogHeader>
          <DialogTitle>Confirm Bet</DialogTitle>
          <DialogDescription>
            Place a real-money bet on Kalshi. This will execute immediately.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-4">
          <div className="rounded-lg bg-surface-raised p-4 space-y-2">
            <p className="text-sm font-medium">
              {market?.question ?? "Unknown market"}
            </p>
            <div className="flex items-center gap-2">
              <Badge
                variant="outline"
                className="text-xs"
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
                {betLabel}
              </Badge>
              <EVBadge ev={rec.ev} size="sm" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-foreground-muted">Amount</p>
              <p className="font-semibold">${betAmount.toFixed(2)}</p>
            </div>
            <div>
              <p className="text-foreground-muted">Market Price</p>
              <p className="font-semibold">{formatPercent(rec.market_price)}</p>
            </div>
            <div>
              <p className="text-foreground-muted">AI Estimate</p>
              <p className="font-semibold">{formatPercent(rec.ai_probability)}</p>
            </div>
            <div>
              <p className="text-foreground-muted">Edge</p>
              <p className="font-semibold" style={{ color: "var(--ev-positive)" }}>
                {formatPercent(rec.edge)}
              </p>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            onClick={handlePlace}
            disabled={isPlacing}
            style={{ backgroundColor: "var(--ev-positive)", color: "black" }}
          >
            {isPlacing ? "Placing..." : `Place $${betAmount.toFixed(2)} Bet`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RecommendationCard({
  rec,
  market,
}: {
  rec: Recommendation;
  market: Market | undefined;
}) {
  const question = market?.question ?? "Unknown market";
  const platform = market?.platform ?? "kalshi";
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
              <CategoryBadge category={market?.category} />
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
                {market?.outcome_label
                  ? `Bet: ${market.outcome_label}`
                  : rec.direction.toUpperCase()}
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
              <div className="flex items-center gap-3" onClick={(e) => e.preventDefault()}>
                <PlaceBetDialog rec={rec} market={market} />
                {market?.platform === "kalshi" && (
                  <a
                    href={getKalshiMarketUrl(market.platform_id)}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="flex items-center gap-1 hover:text-foreground transition-colors"
                  >
                    <ExternalLink className="h-3 w-3" />
                    Kalshi
                  </a>
                )}
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
