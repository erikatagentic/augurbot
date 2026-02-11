"use client";

import { useState } from "react";
import { DollarSign, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCreateTrade } from "@/hooks/use-trades";
import { formatPercent } from "@/lib/utils";
import { useSWRConfig } from "swr";

import type { Recommendation, Market, Platform, Direction } from "@/lib/types";

interface TradeLogDialogProps {
  recommendation?: Recommendation;
  market?: Market;
  marketId?: string;
  trigger?: React.ReactNode;
}

export function TradeLogDialog({
  recommendation,
  market,
  marketId,
  trigger: triggerElement,
}: TradeLogDialogProps) {
  const [open, setOpen] = useState(false);
  const { trigger: createTrade, isCreating } = useCreateTrade();
  const { mutate } = useSWRConfig();

  const resolvedMarketId = marketId ?? recommendation?.market_id ?? "";

  const [platform, setPlatform] = useState<Platform>(
    market?.platform ?? "kalshi"
  );
  const [direction, setDirection] = useState<Direction>(
    recommendation?.direction ?? "yes"
  );
  const [entryPrice, setEntryPrice] = useState(
    recommendation?.market_price
      ? String(recommendation.market_price)
      : ""
  );
  const [amount, setAmount] = useState("");
  const [fees, setFees] = useState("0");
  const [notes, setNotes] = useState("");

  const canSubmit =
    resolvedMarketId &&
    entryPrice &&
    parseFloat(entryPrice) > 0 &&
    amount &&
    parseFloat(amount) > 0;

  async function handleSubmit() {
    if (!canSubmit) return;

    try {
      await createTrade({
        market_id: resolvedMarketId,
        recommendation_id: recommendation?.id,
        platform,
        direction,
        entry_price: parseFloat(entryPrice),
        amount: parseFloat(amount),
        fees_paid: parseFloat(fees) || 0,
        notes: notes || undefined,
      });

      // Revalidate trade-related caches
      mutate("/trades");
      mutate("/trades/open");
      mutate("/trades/portfolio");

      toast.success("Trade logged");
      setOpen(false);
      setAmount("");
      setNotes("");
    } catch {
      toast.error("Failed to log trade");
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {triggerElement ?? (
          <Button size="sm" variant="outline">
            <DollarSign className="h-4 w-4 mr-1" />
            Log Trade
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Log Trade</DialogTitle>
        </DialogHeader>

        {market && (
          <p className="text-sm text-foreground-muted line-clamp-2">
            {market.question}
          </p>
        )}

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
                Platform
              </label>
              <Select
                value={platform}
                onValueChange={(v) => setPlatform(v as Platform)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="kalshi">Kalshi</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
                Direction
              </label>
              <Select
                value={direction}
                onValueChange={(v) => setDirection(v as Direction)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="yes">YES</SelectItem>
                  <SelectItem value="no">NO</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
              Entry Price
            </label>
            <div className="relative">
              <Input
                type="number"
                min="0.01"
                max="0.99"
                step="0.01"
                placeholder="0.42"
                value={entryPrice}
                onChange={(e) => setEntryPrice(e.target.value)}
              />
              {entryPrice && parseFloat(entryPrice) > 0 && (
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-foreground-muted">
                  {formatPercent(parseFloat(entryPrice))}
                </span>
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
                Amount ($)
              </label>
              <Input
                type="number"
                min="0.01"
                step="0.01"
                placeholder="100.00"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
                Fees ($)
              </label>
              <Input
                type="number"
                min="0"
                step="0.01"
                placeholder="0.00"
                value={fees}
                onChange={(e) => setFees(e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
              Notes (optional)
            </label>
            <Input
              placeholder="Why I took this trade..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>

          <Button
            className="w-full"
            onClick={handleSubmit}
            disabled={!canSubmit || isCreating}
          >
            {isCreating ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Logging...
              </>
            ) : (
              "Log Trade"
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
