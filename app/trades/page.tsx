"use client";

import { useState } from "react";
import { Wallet, TrendingUp, DollarSign, Target, BarChart3 } from "lucide-react";
import { Sidebar } from "@/components/layout/sidebar";
import { PageContainer } from "@/components/layout/page-container";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/shared/loading-skeleton";
import { TradeLogDialog } from "@/components/trades/trade-log-dialog";
import { OpenPositions } from "@/components/trades/open-positions";
import { TradeHistoryTable } from "@/components/trades/trade-history-table";
import { usePortfolioStats } from "@/hooks/use-trades";
import { formatCurrency, formatPercent } from "@/lib/utils";

import type { LucideIcon } from "lucide-react";
import type { TradeStatus } from "@/lib/types";

function StatCard({
  label,
  value,
  icon: Icon,
  color,
  isLoading,
}: {
  label: string;
  value: string;
  icon: LucideIcon;
  color: string;
  isLoading: boolean;
}) {
  return (
    <Card>
      <CardContent className="flex items-start justify-between">
        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
            {label}
          </p>
          {isLoading ? (
            <Skeleton className="h-10 w-24" />
          ) : (
            <p className="text-4xl font-[family-name:var(--font-display)] italic tabular-nums">
              {value}
            </p>
          )}
        </div>
        <div
          className="flex h-10 w-10 items-center justify-center rounded-lg"
          style={{
            backgroundColor: `color-mix(in srgb, ${color} 15%, transparent)`,
          }}
        >
          <Icon className="h-5 w-5" style={{ color }} />
        </div>
      </CardContent>
    </Card>
  );
}

const STATUS_TABS: Array<{ label: string; value: TradeStatus | undefined }> = [
  { label: "All", value: undefined },
  { label: "Open", value: "open" },
  { label: "Closed", value: "closed" },
  { label: "Cancelled", value: "cancelled" },
];

export default function TradesPage() {
  const { data: stats, isLoading } = usePortfolioStats();
  const [statusFilter, setStatusFilter] = useState<TradeStatus | undefined>(
    undefined
  );

  const pnlColor =
    (stats?.total_pnl ?? 0) >= 0
      ? "var(--ev-positive)"
      : "var(--ev-negative)";

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 overflow-auto">
        <PageContainer>
          <Header
            title="Trades & Portfolio"
            actions={<TradeLogDialog />}
          />

          <div className="space-y-8">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard
                label="Open Positions"
                value={String(stats?.open_positions ?? 0)}
                icon={Wallet}
                color="var(--ev-moderate)"
                isLoading={isLoading}
              />
              <StatCard
                label="Total Invested"
                value={formatCurrency(stats?.total_invested ?? 0)}
                icon={DollarSign}
                color="var(--platform-kalshi)"
                isLoading={isLoading}
              />
              <StatCard
                label="Realized P&L"
                value={formatCurrency(stats?.realized_pnl ?? 0)}
                icon={TrendingUp}
                color={pnlColor}
                isLoading={isLoading}
              />
              <StatCard
                label="Win Rate"
                value={formatPercent(stats?.win_rate ?? 0)}
                icon={Target}
                color="var(--ev-positive)"
                isLoading={isLoading}
              />
            </div>

            <OpenPositions />

            <section>
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-lg font-medium">Trade History</h2>
                <div className="flex gap-1">
                  {STATUS_TABS.map((tab) => (
                    <Button
                      key={tab.label}
                      variant={
                        statusFilter === tab.value ? "default" : "ghost"
                      }
                      size="sm"
                      className="text-xs"
                      onClick={() => setStatusFilter(tab.value)}
                    >
                      {tab.label}
                    </Button>
                  ))}
                </div>
              </div>
              <TradeHistoryTable statusFilter={statusFilter} />
            </section>
          </div>
        </PageContainer>
      </main>
    </div>
  );
}
