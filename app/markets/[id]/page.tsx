"use client";

import { use, useState } from "react";

import { ArrowLeft, RefreshCw, Wallet, CheckCircle } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import { PageContainer } from "@/components/layout/page-container";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { EVBadge } from "@/components/shared/ev-badge";
import { CardSkeleton } from "@/components/shared/loading-skeleton";
import { EmptyState } from "@/components/shared/empty-state";
import { EdgeIndicator } from "@/components/detail/edge-indicator";
import { AIReasoning } from "@/components/detail/ai-reasoning";
import { PriceChart } from "@/components/detail/price-chart";
import { EstimateHistory } from "@/components/detail/estimate-history";
import { PositionCalculator } from "@/components/detail/position-calculator";
import { TradeLogDialog } from "@/components/trades/trade-log-dialog";

import {
  useMarketDetail,
  useMarketEstimates,
  useMarketSnapshots,
  useRefreshEstimate,
} from "@/hooks/use-markets";
import { manuallyResolveMarket } from "@/lib/api";
import { formatPercent } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { PAGE_TITLES, EMPTY_STATES } from "@/lib/constants";

function MarketDetailContent({ id }: { id: string }) {
  const { data: detail, isLoading: detailLoading, mutate: mutateDetail } = useMarketDetail(id);
  const { data: estimates, isLoading: estimatesLoading, mutate: mutateEstimates } = useMarketEstimates(id);
  const { data: snapshots, isLoading: snapshotsLoading } = useMarketSnapshots(id);
  const { trigger: refreshEstimate, isRefreshing } = useRefreshEstimate(id);

  const isLoading = detailLoading || estimatesLoading || snapshotsLoading;

  async function handleRefresh() {
    await refreshEstimate();
    mutateDetail();
    mutateEstimates();
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <CardSkeleton />
        <div className="grid gap-6 lg:grid-cols-2">
          <CardSkeleton />
          <CardSkeleton />
        </div>
        <CardSkeleton />
      </div>
    );
  }

  if (!detail) {
    return (
      <EmptyState
        title="Market not found"
        description="This market could not be loaded. It may have been removed or the ID is invalid."
      />
    );
  }

  const { market, latest_snapshot, latest_estimate, latest_recommendation } = detail;
  const marketPrice = latest_snapshot?.price_yes ?? null;
  const aiProb = latest_estimate?.probability ?? null;
  const edge =
    marketPrice !== null && aiProb !== null ? aiProb - marketPrice : null;
  const ev = latest_recommendation?.ev ?? (edge !== null ? edge : null);
  const kellyFraction = latest_recommendation?.kelly_fraction ?? 0;
  const direction = latest_recommendation?.direction ?? (edge !== null && edge >= 0 ? "yes" : "no");

  return (
    <div className="space-y-6">
      {/* Market header info */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <PlatformBadge platform={market.platform} />
                {market.status === "resolved" && market.outcome !== null && (
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-xs font-medium",
                      market.outcome
                        ? "bg-[var(--ev-positive)]/10 text-[var(--ev-positive)]"
                        : "bg-[var(--ev-negative)]/10 text-[var(--ev-negative)]"
                    )}
                  >
                    Resolved {market.outcome ? "YES" : "NO"}
                  </span>
                )}
              </div>
              <h2 className="text-xl font-semibold">{market.question}</h2>
              {market.resolution_criteria && (
                <p className="text-sm text-foreground-muted">
                  {market.resolution_criteria}
                </p>
              )}
            </div>
            {ev !== null && <EVBadge ev={ev} />}
          </div>
        </CardContent>
      </Card>

      {/* Two-column layout: price comparison + AI reasoning */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Left column */}
        <div className="space-y-6">
          {/* Price comparison cards */}
          <div className="grid grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
                  Market Price
                </CardTitle>
              </CardHeader>
              <CardContent>
                <span className="text-4xl font-semibold tabular-nums italic font-display">
                  {marketPrice !== null
                    ? formatPercent(marketPrice)
                    : "--"}
                </span>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
                  AI Estimate
                </CardTitle>
              </CardHeader>
              <CardContent>
                <span className="text-4xl font-semibold tabular-nums italic font-display">
                  {aiProb !== null
                    ? formatPercent(aiProb)
                    : "--"}
                </span>
              </CardContent>
            </Card>
          </div>

          {/* Edge indicator */}
          {edge !== null && ev !== null && (
            <Card>
              <CardContent className="pt-6">
                <EdgeIndicator edge={edge} ev={ev} />
              </CardContent>
            </Card>
          )}

          {/* Position calculator */}
          {edge !== null && ev !== null && (
            <PositionCalculator
              marketPrice={marketPrice ?? 0}
              aiProbability={aiProb ?? 0}
              edge={edge}
              ev={ev}
              kellyFraction={kellyFraction}
              direction={direction}
            />
          )}
        </div>

        {/* Right column: AI reasoning */}
        <div>
          {latest_estimate ? (
            <AIReasoning estimate={latest_estimate} />
          ) : (
            <Card>
              <CardContent className="pt-6">
                <EmptyState
                  title="No AI estimate"
                  description={EMPTY_STATES.estimates}
                />
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      {/* Price chart (full width) */}
      <PriceChart
        snapshots={snapshots ?? []}
        estimates={estimates ?? []}
      />

      {/* Estimate history */}
      <EstimateHistory estimates={estimates ?? []} />
    </div>
  );
}

export default function MarketDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  return (
    <div className="flex h-screen bg-background">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <PageContainer>
          <Header
            title={PAGE_TITLES.marketDetail}
            actions={
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" asChild>
                  <Link href="/markets">
                    <ArrowLeft className="h-4 w-4" />
                    Back to Markets
                  </Link>
                </Button>
                <ResolveButton id={id} />
                <TradeLogDialog
                  marketId={id}
                  trigger={
                    <Button variant="outline" size="sm">
                      <Wallet className="h-4 w-4" />
                      Log Trade
                    </Button>
                  }
                />
                <RefreshButton id={id} />
              </div>
            }
          />
          <MarketDetailContent id={id} />
        </PageContainer>
      </main>
    </div>
  );
}

function RefreshButton({ id }: { id: string }) {
  const { trigger: refreshEstimate, isRefreshing } = useRefreshEstimate(id);

  return (
    <Button
      size="sm"
      onClick={() => refreshEstimate()}
      disabled={isRefreshing}
    >
      <RefreshCw className={cn("h-4 w-4", isRefreshing && "animate-spin")} />
      {isRefreshing ? "Refreshing..." : "Refresh Estimate"}
    </Button>
  );
}

function ResolveButton({ id }: { id: string }) {
  const { data: detail, mutate } = useMarketDetail(id);
  const [isResolving, setIsResolving] = useState(false);

  if (!detail || detail.market.status !== "active") return null;

  async function handleResolve(outcome: boolean) {
    setIsResolving(true);
    try {
      await manuallyResolveMarket(id, outcome);
      mutate();
    } finally {
      setIsResolving(false);
    }
  }

  return (
    <div className="flex items-center gap-1">
      <Button
        size="sm"
        variant="outline"
        onClick={() => handleResolve(true)}
        disabled={isResolving}
        className="text-[var(--ev-positive)]"
      >
        <CheckCircle className="h-4 w-4" />
        YES
      </Button>
      <Button
        size="sm"
        variant="outline"
        onClick={() => handleResolve(false)}
        disabled={isResolving}
        className="text-[var(--ev-negative)]"
      >
        <CheckCircle className="h-4 w-4" />
        NO
      </Button>
    </div>
  );
}
