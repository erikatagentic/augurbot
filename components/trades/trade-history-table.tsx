"use client";

import Link from "next/link";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { TradeStatusBadge } from "@/components/shared/trade-status-badge";
import { EmptyState } from "@/components/shared/empty-state";
import { Skeleton } from "@/components/shared/loading-skeleton";
import { useTrades } from "@/hooks/use-trades";
import {
  formatPercent,
  formatCurrency,
  formatRelativeTime,
  truncateText,
} from "@/lib/utils";

import type { TradeStatus } from "@/lib/types";

export function TradeHistoryTable({
  statusFilter,
}: {
  statusFilter?: TradeStatus;
}) {
  const { data, isLoading } = useTrades(statusFilter);

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  const trades = data?.trades ?? [];
  const markets = data?.markets ?? {};

  if (trades.length === 0) {
    return (
      <EmptyState
        title="No trades"
        description="No trades logged yet. Place a trade on a prediction market and log it here to track your performance."
      />
    );
  }

  return (
    <div className="rounded-lg border border-border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[40%]">Market</TableHead>
            <TableHead>Platform</TableHead>
            <TableHead>Side</TableHead>
            <TableHead className="text-right">Entry</TableHead>
            <TableHead className="text-right">Amount</TableHead>
            <TableHead className="text-right">P&L</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Date</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {trades.map((trade) => {
            const market = markets[trade.market_id];
            const question = market?.question ?? "Unknown";
            const pnl = trade.pnl;
            const pnlColor =
              pnl === null
                ? "var(--foreground-muted)"
                : pnl > 0
                  ? "var(--ev-positive)"
                  : pnl < 0
                    ? "var(--ev-negative)"
                    : "var(--foreground-muted)";

            return (
              <TableRow key={trade.id}>
                <TableCell>
                  <Link
                    href={`/markets/${trade.market_id}`}
                    className="text-sm hover:underline"
                  >
                    {truncateText(question, 60)}
                  </Link>
                </TableCell>
                <TableCell>
                  <PlatformBadge platform={trade.platform} />
                </TableCell>
                <TableCell>
                  <Badge
                    variant="outline"
                    className="text-xs px-1.5 py-0 font-medium"
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
                </TableCell>
                <TableCell className="text-right tabular-nums text-sm">
                  {formatPercent(trade.entry_price)}
                </TableCell>
                <TableCell className="text-right tabular-nums text-sm">
                  {formatCurrency(trade.amount)}
                </TableCell>
                <TableCell
                  className="text-right tabular-nums text-sm font-medium"
                  style={{ color: pnlColor }}
                >
                  {pnl !== null
                    ? `${pnl >= 0 ? "+" : ""}${formatCurrency(pnl)}`
                    : "—"}
                </TableCell>
                <TableCell>
                  <TradeStatusBadge status={trade.status} />
                </TableCell>
                <TableCell className="text-right text-xs text-foreground-muted">
                  {formatRelativeTime(trade.created_at)}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
