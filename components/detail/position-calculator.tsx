"use client";

import { useState } from "react";

import { Calculator } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

import { cn, formatPercent, formatCurrency } from "@/lib/utils";

export function PositionCalculator({
  marketPrice,
  aiProbability,
  edge,
  ev,
  kellyFraction,
  direction,
}: {
  marketPrice: number;
  aiProbability: number;
  edge: number;
  ev: number;
  kellyFraction: number;
  direction: string;
}) {
  const [bankroll, setBankroll] = useState(10000);

  const recommendedBet = Math.max(0, kellyFraction * bankroll);
  const isYes = direction === "yes";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <Calculator className="h-5 w-5 text-primary" />
          Position Calculator
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <label className="mb-1.5 block text-xs font-medium uppercase tracking-widest text-foreground-muted">
            Bankroll
          </label>
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-foreground-subtle">
              $
            </span>
            <Input
              type="number"
              min={0}
              step={100}
              value={bankroll}
              onChange={(e) => setBankroll(Number(e.target.value) || 0)}
              className="pl-7 tabular-nums"
            />
          </div>
        </div>

        <div className="space-y-3 rounded-lg border border-border bg-surface p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
              Direction
            </span>
            <span
              className={cn(
                "text-sm font-semibold",
                isYes ? "text-[var(--ev-positive)]" : "text-[var(--ev-negative)]"
              )}
            >
              {direction.toUpperCase()}
            </span>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
              Edge
            </span>
            <span className="text-sm tabular-nums">
              {edge > 0 ? "+" : ""}
              {formatPercent(edge)}
            </span>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
              Expected Value
            </span>
            <span className="text-sm tabular-nums">
              {ev > 0 ? "+" : ""}
              {formatPercent(ev)}
            </span>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
              Kelly Fraction
            </span>
            <span className="text-sm tabular-nums">
              {formatPercent(kellyFraction)}
            </span>
          </div>

          <div className="border-t border-border pt-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
                Recommended Bet
              </span>
              <span className="text-xl font-semibold tabular-nums">
                {formatCurrency(recommendedBet)}
              </span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
