"use client";

import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { TradeStatusBadge } from "@/components/shared/trade-status-badge";
import { EmptyState } from "@/components/shared/empty-state";
import { CardSkeleton } from "@/components/shared/loading-skeleton";
import { useOpenTrades } from "@/hooks/use-trades";
import { formatPercent, formatCurrency, truncateText } from "@/lib/utils";

export function OpenPositions() {
  const { data, isLoading } = useOpenTrades();

  if (isLoading) {
    return (
      <section>
        <h2 className="mb-4 text-lg font-medium">Open Positions</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 2 }).map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      </section>
    );
  }

  const trades = data?.trades ?? [];
  const markets = data?.markets ?? {};

  if (trades.length === 0) {
    return (
      <section>
        <h2 className="mb-4 text-lg font-medium">Open Positions</h2>
        <EmptyState
          title="No open positions"
          description="Log a trade to start tracking your portfolio."
        />
      </section>
    );
  }

  return (
    <section>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-medium">Open Positions</h2>
        <Link
          href="/trades"
          className="text-xs text-foreground-muted hover:text-foreground transition-colors"
        >
          View all trades
        </Link>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {trades.slice(0, 6).map((trade) => {
          const market = markets[trade.market_id];
          const question = market?.question ?? "Unknown market";
          const platform = market?.platform ?? trade.platform;

          return (
            <Link
              key={trade.id}
              href={`/markets/${trade.market_id}`}
              className="block"
            >
              <Card className="transition-colors hover:border-border-hover">
                <CardContent className="space-y-3">
                  <p className="text-sm font-medium leading-snug">
                    {truncateText(question, 80)}
                  </p>

                  <div className="flex flex-wrap items-center gap-2">
                    <PlatformBadge platform={platform} />
                    <Badge
                      variant="outline"
                      className="text-xs px-2 py-0.5 font-medium"
                      style={{
                        borderColor:
                          trade.direction === "yes"
                            ? "var(--ev-positive)"
                            : "var(--ev-negative)",
                        color:
                          trade.direction === "yes"
                            ? "var(--ev-positive)"
                            : "var(--ev-negative)",
                      }}
                    >
                      {trade.direction.toUpperCase()}
                    </Badge>
                    <TradeStatusBadge status={trade.status} />
                  </div>

                  <div className="grid grid-cols-2 gap-3 rounded-lg bg-surface-raised p-3">
                    <div>
                      <p className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
                        Entry
                      </p>
                      <p className="mt-1 text-lg font-semibold tabular-nums">
                        {formatPercent(trade.entry_price)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
                        Amount
                      </p>
                      <p className="mt-1 text-lg font-semibold tabular-nums">
                        {formatCurrency(trade.amount)}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
