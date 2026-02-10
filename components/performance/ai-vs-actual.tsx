"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/shared/loading-skeleton";
import { EmptyState } from "@/components/shared/empty-state";
import { useAIvsActual } from "@/hooks/use-trades";
import { formatPercent, formatCurrency, truncateText } from "@/lib/utils";

function ComparisonStat({
  label,
  aiValue,
  actualValue,
  formatter,
}: {
  label: string;
  aiValue: number;
  actualValue: number;
  formatter: (v: number) => string;
}) {
  const aiColor = "var(--platform-polymarket)";
  const actualColor = "var(--ev-positive)";

  return (
    <div className="space-y-2 rounded-lg bg-surface-raised p-4">
      <p className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
        {label}
      </p>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <p className="text-xs text-foreground-muted">AI Recs</p>
          <p
            className="text-2xl font-semibold tabular-nums"
            style={{ color: aiColor }}
          >
            {formatter(aiValue)}
          </p>
        </div>
        <div>
          <p className="text-xs text-foreground-muted">Your Trades</p>
          <p
            className="text-2xl font-semibold tabular-nums"
            style={{ color: actualColor }}
          >
            {formatter(actualValue)}
          </p>
        </div>
      </div>
    </div>
  );
}

export function AIvsActualComparison() {
  const { data, isLoading } = useAIvsActual();

  if (isLoading) {
    return (
      <section>
        <h2 className="mb-4 text-lg font-medium">AI vs Your Trades</h2>
        <Skeleton className="h-64 w-full" />
      </section>
    );
  }

  if (!data || (data.total_ai_recommendations === 0 && data.comparison_rows.length === 0)) {
    return (
      <section>
        <h2 className="mb-4 text-lg font-medium">AI vs Your Trades</h2>
        <EmptyState
          title="No comparison data"
          description="Start logging trades to compare your performance against AI recommendations."
        />
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <h2 className="text-lg font-medium">AI vs Your Trades</h2>

      <div className="grid gap-4 sm:grid-cols-2">
        <ComparisonStat
          label="Hit Rate"
          aiValue={data.ai_hit_rate}
          actualValue={data.actual_hit_rate}
          formatter={formatPercent}
        />
        <ComparisonStat
          label="Avg Return"
          aiValue={data.ai_avg_edge}
          actualValue={data.actual_avg_return}
          formatter={formatPercent}
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
              AI Recommendations
            </p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">
              {data.total_ai_recommendations}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
              You Traded
            </p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">
              {data.recommendations_traded}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
              AI Brier Score
            </p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">
              {data.ai_brier_score.toFixed(3)}
            </p>
          </CardContent>
        </Card>
      </div>

      {data.comparison_rows.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Trade-by-Trade Comparison</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="rounded-lg border border-border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[40%]">Market</TableHead>
                    <TableHead>Your Side</TableHead>
                    <TableHead>AI Side</TableHead>
                    <TableHead className="text-right">Your P&L</TableHead>
                    <TableHead className="text-right">Return</TableHead>
                    <TableHead>Followed AI?</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.comparison_rows.map((row, i) => {
                    const pnlColor =
                      row.trade_pnl === null
                        ? "var(--foreground-muted)"
                        : (row.trade_pnl ?? 0) > 0
                          ? "var(--ev-positive)"
                          : (row.trade_pnl ?? 0) < 0
                            ? "var(--ev-negative)"
                            : "var(--foreground-muted)";

                    return (
                      <TableRow key={i}>
                        <TableCell className="text-sm">
                          {truncateText(row.question, 50)}
                        </TableCell>
                        <TableCell
                          className="text-sm font-medium"
                          style={{
                            color:
                              row.trade_direction === "yes"
                                ? "var(--ev-positive)"
                                : "var(--ev-negative)",
                          }}
                        >
                          {row.trade_direction.toUpperCase()}
                        </TableCell>
                        <TableCell
                          className="text-sm font-medium"
                          style={{
                            color: row.ai_direction
                              ? row.ai_direction === "yes"
                                ? "var(--ev-positive)"
                                : "var(--ev-negative)"
                              : "var(--foreground-muted)",
                          }}
                        >
                          {row.ai_direction
                            ? row.ai_direction.toUpperCase()
                            : "—"}
                        </TableCell>
                        <TableCell
                          className="text-right tabular-nums text-sm font-medium"
                          style={{ color: pnlColor }}
                        >
                          {row.trade_pnl !== null
                            ? `${(row.trade_pnl ?? 0) >= 0 ? "+" : ""}${formatCurrency(row.trade_pnl ?? 0)}`
                            : "—"}
                        </TableCell>
                        <TableCell
                          className="text-right tabular-nums text-sm"
                          style={{ color: pnlColor }}
                        >
                          {formatPercent(row.trade_return)}
                        </TableCell>
                        <TableCell className="text-sm">
                          {row.followed_ai === null
                            ? "—"
                            : row.followed_ai
                              ? "Yes"
                              : "No"}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}
    </section>
  );
}
