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
import { EVBadge } from "@/components/shared/ev-badge";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { EmptyState } from "@/components/shared/empty-state";
import { TableSkeleton } from "@/components/shared/loading-skeleton";

import { formatPercent, formatRelativeTime, truncateText, getEvColor } from "@/lib/utils";
import { EMPTY_STATES } from "@/lib/constants";

import type { Market, MarketSnapshot, AIEstimate, Recommendation } from "@/lib/types";

interface MarketTableRow {
  market: Market;
  snapshot: MarketSnapshot | null;
  estimate: AIEstimate | null;
  recommendation: Recommendation | null;
}

export function MarketTable({
  markets,
  isLoading,
}: {
  markets: MarketTableRow[];
  isLoading: boolean;
}) {
  if (isLoading) {
    return <TableSkeleton rows={8} />;
  }

  if (!markets.length) {
    return (
      <EmptyState
        title="No markets found"
        description={EMPTY_STATES.markets}
      />
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="min-w-[280px]">Question</TableHead>
          <TableHead>Platform</TableHead>
          <TableHead className="text-right">Market Price</TableHead>
          <TableHead className="text-right">AI Estimate</TableHead>
          <TableHead className="text-right">Edge</TableHead>
          <TableHead>EV</TableHead>
          <TableHead className="text-right">Close Date</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {markets.map((row) => {
          const marketPrice = row.snapshot?.price_yes ?? null;
          const aiProb = row.estimate?.probability ?? null;
          const edge =
            marketPrice !== null && aiProb !== null
              ? aiProb - marketPrice
              : null;
          const ev = row.recommendation?.ev ?? (edge !== null ? edge : null);

          return (
            <TableRow key={row.market.id} className="cursor-pointer">
              <TableCell>
                <Link
                  href={`/markets/${row.market.id}`}
                  className="block hover:underline"
                >
                  <span className="text-sm text-foreground">
                    {truncateText(row.market.question, 80)}
                  </span>
                </Link>
              </TableCell>
              <TableCell>
                <PlatformBadge platform={row.market.platform} />
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {marketPrice !== null ? (
                  <span className="text-sm">{formatPercent(marketPrice)}</span>
                ) : (
                  <span className="text-sm text-foreground-subtle">--</span>
                )}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {aiProb !== null ? (
                  <span className="text-sm">{formatPercent(aiProb)}</span>
                ) : (
                  <span className="text-sm text-foreground-subtle">--</span>
                )}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {edge !== null ? (
                  <span
                    className="text-sm font-medium"
                    style={{ color: getEvColor(edge) }}
                  >
                    {edge > 0 ? "+" : ""}
                    {formatPercent(edge)}
                  </span>
                ) : (
                  <span className="text-sm text-foreground-subtle">--</span>
                )}
              </TableCell>
              <TableCell>
                {ev !== null ? (
                  <EVBadge ev={ev} size="sm" />
                ) : (
                  <span className="text-sm text-foreground-subtle">--</span>
                )}
              </TableCell>
              <TableCell className="text-right">
                {row.market.close_date ? (
                  <span className="text-sm text-foreground-muted">
                    {formatRelativeTime(row.market.close_date)}
                  </span>
                ) : (
                  <span className="text-sm text-foreground-subtle">--</span>
                )}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
