"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { Loader2, CheckCircle, AlertCircle, Bell } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Sidebar } from "@/components/layout/sidebar";
import { PageContainer } from "@/components/layout/page-container";
import { Header } from "@/components/layout/header";
import { Skeleton } from "@/components/shared/loading-skeleton";
import { useConfig, useUpdateConfig, useHealth, useCostSummary } from "@/hooks/use-performance";
import { useScanTrigger, useResolutionCheckTrigger, useTradeSyncTrigger, useTradeSyncStatus } from "@/hooks/use-recommendations";
import { cn, formatPercent, formatCurrency } from "@/lib/utils";
import { sendTestNotification } from "@/lib/api";
import { DEFAULT_CONFIG, PAGE_TITLES, PLATFORM_CONFIG } from "@/lib/constants";

import type { AppConfig, Platform } from "@/lib/types";

function RiskParameters({
  config,
  onUpdate,
}: {
  config: AppConfig;
  onUpdate: (patch: Partial<AppConfig>) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Risk Parameters</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium">Kelly Fraction</label>
            <span className="text-sm tabular-nums text-foreground-muted">
              {formatPercent(config.kelly_fraction)}
            </span>
          </div>
          <Slider
            value={[config.kelly_fraction]}
            min={0.25}
            max={0.5}
            step={0.01}
            onValueChange={([value]) => onUpdate({ kelly_fraction: value })}
          />
          <p className="mt-1 text-xs text-foreground-subtle">
            Fraction of full Kelly to use (25%&ndash;50%)
          </p>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium">Minimum Edge</label>
            <span className="text-sm tabular-nums text-foreground-muted">
              {formatPercent(config.min_edge_threshold)}
            </span>
          </div>
          <Slider
            value={[config.min_edge_threshold]}
            min={0.01}
            max={0.2}
            step={0.01}
            onValueChange={([value]) =>
              onUpdate({ min_edge_threshold: value })
            }
          />
          <p className="mt-1 text-xs text-foreground-subtle">
            Only recommend bets with at least this much edge (1%&ndash;20%)
          </p>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium">Max Single Bet</label>
            <span className="text-sm tabular-nums text-foreground-muted">
              {formatPercent(config.max_single_bet_fraction)}
            </span>
          </div>
          <Slider
            value={[config.max_single_bet_fraction]}
            min={0.01}
            max={0.1}
            step={0.01}
            onValueChange={([value]) =>
              onUpdate({ max_single_bet_fraction: value })
            }
          />
          <p className="mt-1 text-xs text-foreground-subtle">
            Max bet as a fraction of bankroll (1%&ndash;10%)
          </p>
        </div>

        <div>
          <label className="text-sm font-medium">Bankroll</label>
          <div className="mt-2">
            <Input
              type="number"
              value={config.bankroll}
              min={0}
              step={100}
              onChange={(e) =>
                onUpdate({ bankroll: Number(e.target.value) || 0 })
              }
              className="max-w-xs"
            />
          </div>
          <p className="mt-1 text-xs text-foreground-subtle">
            Your total capital for position sizing
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function ScanSettings({
  config,
  onUpdate,
}: {
  config: AppConfig;
  onUpdate: (patch: Partial<AppConfig>) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Scan Settings</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <div>
          <label className="text-sm font-medium">Scan Schedule (Pacific Time)</label>
          <p className="mt-1 text-xs text-foreground-subtle">
            Choose when to run scans. Each scan costs ~$1 in API calls.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {[6, 8, 10, 12, 14, 16, 18, 20].map((hour) => {
              const times = config.scan_times ?? [8, 14];
              const isActive = times.includes(hour);
              const label =
                hour === 0
                  ? "12 AM"
                  : hour < 12
                    ? `${hour} AM`
                    : hour === 12
                      ? "12 PM"
                      : `${hour - 12} PM`;
              return (
                <button
                  key={hour}
                  type="button"
                  onClick={() => {
                    const next = isActive
                      ? times.filter((h) => h !== hour)
                      : [...times, hour].sort((a, b) => a - b);
                    if (next.length > 0) {
                      onUpdate({ scan_times: next });
                    }
                  }}
                  className={cn(
                    "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                    isActive
                      ? "bg-primary/20 text-primary border border-primary/40"
                      : "bg-surface-raised text-foreground-subtle border border-border hover:border-border-hover"
                  )}
                >
                  {label}
                </button>
              );
            })}
          </div>
          <p className="mt-2 text-xs text-foreground-subtle">
            {(config.scan_times ?? [8, 14]).length} scan
            {(config.scan_times ?? [8, 14]).length === 1 ? "" : "s"}/day
          </p>
        </div>

        <div>
          <label className="text-sm font-medium">Minimum Volume</label>
          <div className="mt-2">
            <Input
              type="number"
              value={config.min_volume}
              min={0}
              step={1000}
              onChange={(e) =>
                onUpdate({ min_volume: Number(e.target.value) || 0 })
              }
              className="max-w-xs"
            />
          </div>
          <p className="mt-1 text-xs text-foreground-subtle">
            Only scan markets with at least this much volume (USD)
          </p>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium">Markets per Platform</label>
            <span className="text-sm tabular-nums text-foreground-muted">
              {config.markets_per_platform}
            </span>
          </div>
          <Slider
            value={[config.markets_per_platform]}
            min={10}
            max={100}
            step={5}
            onValueChange={([value]) =>
              onUpdate({ markets_per_platform: value })
            }
          />
          <p className="mt-1 text-xs text-foreground-subtle">
            Max markets fetched per platform per scan (affects API cost)
          </p>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium">Web Searches per Estimate</label>
            <span className="text-sm tabular-nums text-foreground-muted">
              {config.web_search_max_uses}
            </span>
          </div>
          <Slider
            value={[config.web_search_max_uses]}
            min={1}
            max={5}
            step={1}
            onValueChange={([value]) =>
              onUpdate({ web_search_max_uses: value })
            }
          />
          <p className="mt-1 text-xs text-foreground-subtle">
            Max web searches Claude can use per market (fewer = cheaper)
          </p>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium">Estimate Cache (hours)</label>
            <span className="text-sm tabular-nums text-foreground-muted">
              {config.estimate_cache_hours}h
            </span>
          </div>
          <Slider
            value={[config.estimate_cache_hours]}
            min={6}
            max={48}
            step={2}
            onValueChange={([value]) =>
              onUpdate({ estimate_cache_hours: value })
            }
          />
          <p className="mt-1 text-xs text-foreground-subtle">
            Skip re-research if an estimate exists within this window
          </p>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium">
              Re-estimate Trigger
            </label>
            <span className="text-sm tabular-nums text-foreground-muted">
              {formatPercent(config.re_estimate_trigger)}
            </span>
          </div>
          <Slider
            value={[config.re_estimate_trigger]}
            min={0.02}
            max={0.1}
            step={0.01}
            onValueChange={([value]) =>
              onUpdate({ re_estimate_trigger: value })
            }
          />
          <p className="mt-1 text-xs text-foreground-subtle">
            Re-research when market price moves by this amount (2%&ndash;10%)
          </p>
        </div>

        <div className="flex items-center justify-between py-2">
          <div>
            <span className="text-sm font-medium">Price Movement Checks</span>
            <p className="text-xs text-foreground-subtle">
              Periodically check for price swings and re-estimate
            </p>
          </div>
          <Switch
            checked={config.price_check_enabled}
            onCheckedChange={(checked) =>
              onUpdate({ price_check_enabled: checked })
            }
          />
        </div>

        <div className="flex items-center justify-between py-2">
          <div>
            <span className="text-sm font-medium">Resolution Detection</span>
            <p className="text-xs text-foreground-subtle">
              Auto-detect when markets resolve and track performance (free)
            </p>
          </div>
          <Switch
            checked={config.resolution_check_enabled}
            onCheckedChange={(checked) =>
              onUpdate({ resolution_check_enabled: checked })
            }
          />
        </div>

        {config.resolution_check_enabled && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium">Resolution Check Interval</label>
              <span className="text-sm tabular-nums text-foreground-muted">
                {config.resolution_check_interval_hours}h
              </span>
            </div>
            <Slider
              value={[config.resolution_check_interval_hours]}
              min={1}
              max={24}
              step={1}
              onValueChange={([value]) =>
                onUpdate({ resolution_check_interval_hours: value })
              }
            />
            <p className="mt-1 text-xs text-foreground-subtle">
              How often to check platforms for resolved markets (no API cost)
            </p>
          </div>
        )}

        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium">Max Close Date Window</label>
            <span className="text-sm tabular-nums text-foreground-muted">
              {config.max_close_hours}h
            </span>
          </div>
          <Slider
            value={[config.max_close_hours]}
            min={12}
            max={72}
            step={6}
            onValueChange={([value]) =>
              onUpdate({ max_close_hours: value })
            }
          />
          <p className="mt-1 text-xs text-foreground-subtle">
            Only scan markets closing within this window (12h&ndash;72h). Lower = daily sports, higher = weekend games.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function CostTracker() {
  const { data: costs, isLoading } = useCostSummary();

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>API Costs</CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-20 w-full" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>API Costs</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-4">
          <div className="rounded-lg bg-surface-raised p-3">
            <p className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
              Today
            </p>
            <p className="mt-1 text-lg font-semibold tabular-nums">
              {formatCurrency(costs?.total_cost_today ?? 0)}
            </p>
          </div>
          <div className="rounded-lg bg-surface-raised p-3">
            <p className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
              This Week
            </p>
            <p className="mt-1 text-lg font-semibold tabular-nums">
              {formatCurrency(costs?.total_cost_week ?? 0)}
            </p>
          </div>
          <div className="rounded-lg bg-surface-raised p-3">
            <p className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
              This Month
            </p>
            <p className="mt-1 text-lg font-semibold tabular-nums">
              {formatCurrency(costs?.total_cost_month ?? 0)}
            </p>
          </div>
          <div className="rounded-lg bg-surface-raised p-3">
            <p className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
              All Time
            </p>
            <p className="mt-1 text-lg font-semibold tabular-nums">
              {formatCurrency(costs?.total_cost_all_time ?? 0)}
            </p>
          </div>
        </div>
        <div className="flex items-center justify-between text-sm text-foreground-muted pt-2">
          <span>Avg cost per scan</span>
          <span className="tabular-nums">{formatCurrency(costs?.cost_per_scan_avg ?? 0)}</span>
        </div>
        <div className="flex items-center justify-between text-sm text-foreground-muted">
          <span>Total API calls</span>
          <span className="tabular-nums">{costs?.total_api_calls ?? 0}</span>
        </div>
      </CardContent>
    </Card>
  );
}

function PlatformToggles({
  config,
  onUpdate,
}: {
  config: AppConfig;
  onUpdate: (patch: Partial<AppConfig>) => void;
}) {
  const { data: health } = useHealth();
  const platforms = config.platforms_enabled ?? {};

  function togglePlatform(platform: string, enabled: boolean) {
    onUpdate({
      platforms_enabled: {
        ...platforms,
        [platform]: enabled,
      },
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Platform Toggles</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between py-2">
          <div className="flex items-center gap-3">
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: "var(--platform-kalshi)" }}
            />
            <span className="text-sm font-medium">Kalshi</span>
            <span className="flex items-center gap-1 text-xs text-foreground-muted">
              {health?.platforms?.kalshi ? (
                <>
                  <CheckCircle
                    className="h-3 w-3"
                    style={{ color: "var(--ev-positive)" }}
                  />
                  Connected
                </>
              ) : (
                <>
                  <AlertCircle
                    className="h-3 w-3"
                    style={{ color: "var(--foreground-subtle)" }}
                  />
                  Unknown
                </>
              )}
            </span>
          </div>
          <Switch
            checked={platforms.kalshi ?? true}
            onCheckedChange={(checked) =>
              togglePlatform("kalshi", checked)
            }
          />
        </div>
      </CardContent>
    </Card>
  );
}

function TradeSyncSettings({
  config,
  onUpdate,
}: {
  config: AppConfig;
  onUpdate: (patch: Partial<AppConfig>) => void;
}) {
  const { trigger: syncNow, isSyncing } = useTradeSyncTrigger();
  const { data: syncStatus, mutate: refreshStatus } = useTradeSyncStatus();

  async function handleSync() {
    try {
      await syncNow();
      toast.success("Trade sync started");
      setTimeout(() => refreshStatus(), 3000);
    } catch {
      toast.error("Failed to start trade sync");
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Trade Sync</CardTitle>
          <Button
            size="sm"
            onClick={handleSync}
            disabled={isSyncing}
          >
            {isSyncing ? (
              <>
                <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                Syncing...
              </>
            ) : (
              "Sync Now"
            )}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex items-center justify-between py-2">
          <div>
            <span className="text-sm font-medium">Auto-Sync Trades</span>
            <p className="text-xs text-foreground-subtle">
              Automatically import trades from connected platforms
            </p>
          </div>
          <Switch
            checked={config.trade_sync_enabled}
            onCheckedChange={(checked) =>
              onUpdate({ trade_sync_enabled: checked })
            }
          />
        </div>

        {config.trade_sync_enabled && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium">Sync Interval</label>
              <span className="text-sm tabular-nums text-foreground-muted">
                {config.trade_sync_interval_hours}h
              </span>
            </div>
            <Slider
              value={[config.trade_sync_interval_hours]}
              min={1}
              max={24}
              step={1}
              onValueChange={([value]) =>
                onUpdate({ trade_sync_interval_hours: value })
              }
            />
          </div>
        )}

        <div className="flex items-center justify-between py-2">
          <div>
            <span className="text-sm font-medium">Kalshi RSA Auth</span>
            <p className="text-xs text-foreground-subtle">
              Set KALSHI_API_KEY and KALSHI_PRIVATE_KEY_PATH env vars on Railway
            </p>
          </div>
          <span className="flex items-center gap-1.5 text-xs">
            <span
              className="h-2 w-2 rounded-full"
              style={{
                backgroundColor: config.kalshi_rsa_configured
                  ? "var(--ev-positive)"
                  : "var(--foreground-subtle)",
              }}
            />
            {config.kalshi_rsa_configured ? "Configured" : "Not configured"}
          </span>
        </div>

        {/* Last sync status — Kalshi only */}
        {syncStatus?.platforms?.kalshi && (
          <div className="space-y-2 pt-2 border-t border-border">
            <p className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
              Last Sync
            </p>
            <div className="flex items-center justify-between text-sm">
              <span>Kalshi</span>
              <span className="text-xs text-foreground-muted">
                {syncStatus.platforms.kalshi.status === "completed" ? (
                  <>
                    {syncStatus.platforms.kalshi.trades_created} new, {syncStatus.platforms.kalshi.trades_skipped} skipped
                    {syncStatus.platforms.kalshi.completed_at && (
                      <> &middot; {new Date(syncStatus.platforms.kalshi.completed_at).toLocaleString()}</>
                    )}
                  </>
                ) : syncStatus.platforms.kalshi.status === "failed" ? (
                  <span style={{ color: "var(--ev-negative)" }}>
                    Failed: {syncStatus.platforms.kalshi.error_message?.slice(0, 80)}
                  </span>
                ) : (
                  syncStatus.platforms.kalshi.status
                )}
              </span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function AutoTradeSettings({
  config,
  onUpdate,
}: {
  config: AppConfig;
  onUpdate: (patch: Partial<AppConfig>) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Auto-Trade</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex items-center justify-between py-2">
          <div>
            <span className="text-sm font-medium">Enable Auto-Trade</span>
            <p className="text-xs text-foreground-subtle">
              Automatically place bets on Kalshi when a scan finds high-EV
              recommendations
            </p>
          </div>
          <Switch
            checked={config.auto_trade_enabled}
            onCheckedChange={(checked) =>
              onUpdate({ auto_trade_enabled: checked })
            }
          />
        </div>

        {config.auto_trade_enabled && (
          <>
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-medium">Minimum EV</label>
                <span className="text-sm tabular-nums text-foreground-muted">
                  {formatPercent(config.auto_trade_min_ev)}
                </span>
              </div>
              <Slider
                value={[config.auto_trade_min_ev]}
                min={0.01}
                max={0.2}
                step={0.01}
                onValueChange={([value]) =>
                  onUpdate({ auto_trade_min_ev: value })
                }
              />
              <p className="mt-1 text-xs text-foreground-subtle">
                Only auto-trade recommendations with at least this much EV
              </p>
            </div>

            <div className="rounded-lg bg-surface-raised p-4 space-y-2">
              <p className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
                How it works
              </p>
              <ul className="text-xs text-foreground-muted space-y-1 list-disc pl-4">
                <li>After each scan, bets are placed for recommendations above the minimum EV</li>
                <li>Bet size is calculated using Kelly fraction, capped at your max single bet setting</li>
                <li>Minimum bet is $1 per trade</li>
                <li>All auto-trades are logged and visible in the Trades tab</li>
              </ul>
            </div>

            {!config.kalshi_rsa_configured && (
              <div
                className="rounded-lg p-3 text-sm"
                style={{
                  backgroundColor: "hsl(43 96% 56% / 0.1)",
                  color: "var(--ev-moderate)",
                }}
              >
                Kalshi RSA auth is not configured. Auto-trade requires
                KALSHI_API_KEY and KALSHI_PRIVATE_KEY_PATH environment variables
                on Railway.
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function NotificationSettings({
  config,
  onUpdate,
}: {
  config: AppConfig;
  onUpdate: (patch: Partial<AppConfig>) => void;
}) {
  const [isTesting, setIsTesting] = useState(false);

  async function handleTestNotification() {
    setIsTesting(true);
    try {
      const result = await sendTestNotification();
      const channels = Object.entries(result.channels || {})
        .map(([ch, ok]) => `${ch}: ${ok ? "sent" : "failed"}`)
        .join(", ");
      toast.success(`Test notification sent (${channels})`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      toast.error(`Test failed: ${msg}`);
    } finally {
      setIsTesting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Bell className="h-4 w-4" />
            Notifications
          </CardTitle>
          {config.notifications_enabled && (
            <Button
              size="sm"
              variant="outline"
              onClick={handleTestNotification}
              disabled={isTesting}
            >
              {isTesting ? (
                <>
                  <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                  Sending...
                </>
              ) : (
                "Send Test"
              )}
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex items-center justify-between py-2">
          <div>
            <span className="text-sm font-medium">Enable Notifications</span>
            <p className="text-xs text-foreground-subtle">
              Get alerted when scans find high-EV bets
            </p>
          </div>
          <Switch
            checked={config.notifications_enabled}
            onCheckedChange={(checked) =>
              onUpdate({ notifications_enabled: checked })
            }
          />
        </div>

        {config.notifications_enabled && (
          <>
            <div>
              <label className="text-sm font-medium">Email Address</label>
              <div className="mt-2">
                <Input
                  type="email"
                  placeholder="you@example.com"
                  value={config.notification_email}
                  onChange={(e) =>
                    onUpdate({ notification_email: e.target.value })
                  }
                  className="max-w-sm"
                />
              </div>
              <p className="mt-1 text-xs text-foreground-subtle">
                Requires RESEND_API_KEY env var on Railway
              </p>
            </div>

            <div>
              <label className="text-sm font-medium">Slack Webhook URL</label>
              <div className="mt-2">
                <Input
                  type="url"
                  placeholder="https://hooks.slack.com/services/..."
                  value={config.notification_slack_webhook}
                  onChange={(e) =>
                    onUpdate({ notification_slack_webhook: e.target.value })
                  }
                  className="max-w-sm"
                />
              </div>
              <p className="mt-1 text-xs text-foreground-subtle">
                Create an incoming webhook in your Slack workspace settings
              </p>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-medium">Minimum EV to Notify</label>
                <span className="text-sm tabular-nums text-foreground-muted">
                  {formatPercent(config.notification_min_ev)}
                </span>
              </div>
              <Slider
                value={[config.notification_min_ev]}
                min={0.01}
                max={0.2}
                step={0.01}
                onValueChange={([value]) =>
                  onUpdate({ notification_min_ev: value })
                }
              />
              <p className="mt-1 text-xs text-foreground-subtle">
                Only notify for recommendations with at least this much EV
              </p>
            </div>

            <div className="flex items-center justify-between py-2">
              <div>
                <span className="text-sm font-medium">Daily Digest (9 PM PT)</span>
                <p className="text-xs text-foreground-subtle">
                  Nightly summary of recommendations, trades, resolutions, and P&L
                </p>
              </div>
              <Switch
                checked={config.daily_digest_enabled}
                onCheckedChange={(checked) =>
                  onUpdate({ daily_digest_enabled: checked })
                }
              />
            </div>

            <div className="rounded-lg bg-surface-raised p-4 space-y-2">
              <p className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
                How it works
              </p>
              <ul className="text-xs text-foreground-muted space-y-1 list-disc pl-4">
                <li>After each scheduled or manual scan, notifications are sent for new high-EV recommendations</li>
                <li>Daily digest sends a nightly summary at 9 PM PT (if there was any activity)</li>
                <li>Configure one or both channels (email and Slack)</li>
                <li>Use the &ldquo;Send Test&rdquo; button to verify your setup</li>
              </ul>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function ApiStatus() {
  const { data: health, isLoading } = useHealth();
  const { trigger: scan, isScanning } = useScanTrigger();
  const { trigger: checkResolutions, isChecking } = useResolutionCheckTrigger();

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>API Status</CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-20 w-full" />
        </CardContent>
      </Card>
    );
  }

  const dbConnected = health?.database_connected ?? false;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>API Status</CardTitle>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={async () => {
                try {
                  await checkResolutions();
                  toast.success("Resolution check started");
                } catch {
                  toast.error("Failed to start resolution check");
                }
              }}
              disabled={isChecking}
            >
              {isChecking ? (
                <>
                  <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                  Checking...
                </>
              ) : (
                "Check Resolutions"
              )}
            </Button>
            <Button
              size="sm"
              onClick={async () => {
                try {
                  await scan();
                  toast.success("Scan started");
                } catch {
                  toast.error("Failed to start scan");
                }
              }}
              disabled={isScanning}
            >
              {isScanning ? (
                <>
                  <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                  Scanning...
                </>
              ) : (
                "Scan Now"
              )}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm">Database</span>
          <span className="flex items-center gap-1.5 text-xs">
            <span
              className="h-2 w-2 rounded-full"
              style={{
                backgroundColor: dbConnected
                  ? "var(--ev-positive)"
                  : "var(--ev-negative)",
              }}
            />
            {dbConnected ? "Connected" : "Disconnected"}
          </span>
        </div>

        {health?.platforms &&
          Object.entries(health.platforms).map(([platform, connected]) => (
            <div key={platform} className="flex items-center justify-between">
              <span className="text-sm capitalize">{platform}</span>
              <span className="flex items-center gap-1.5 text-xs">
                <span
                  className="h-2 w-2 rounded-full"
                  style={{
                    backgroundColor: connected
                      ? "var(--ev-positive)"
                      : "var(--ev-negative)",
                  }}
                />
                {connected ? "OK" : "Error"}
              </span>
            </div>
          ))}

        {health?.last_scan_at && (
          <p className="pt-2 text-xs text-foreground-muted">
            Last scan:{" "}
            {new Date(health.last_scan_at).toLocaleString()}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export default function SettingsPage() {
  const { data: serverConfig, isLoading, mutate } = useConfig();
  const { trigger: updateConfigOnServer } = useUpdateConfig();

  const [localConfig, setLocalConfig] = useState<AppConfig>(
    DEFAULT_CONFIG as AppConfig
  );

  useEffect(() => {
    if (serverConfig) {
      setLocalConfig(serverConfig);
    }
  }, [serverConfig]);

  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const handleUpdate = useCallback(
    (patch: Partial<AppConfig>) => {
      setLocalConfig((prev) => ({ ...prev, ...patch }));

      clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        updateConfigOnServer(patch)
          .then(() => mutate())
          .catch(() => {
            toast.error("Failed to save setting");
            if (serverConfig) setLocalConfig(serverConfig);
          });
      }, 300);
    },
    [updateConfigOnServer, mutate, serverConfig]
  );

  if (isLoading) {
    return (
      <div className="flex min-h-screen">
        <Sidebar />
        <main className="flex-1 overflow-auto">
          <PageContainer>
            <Header title={PAGE_TITLES.settings} />
            <div className="grid gap-6 lg:grid-cols-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <Card key={i}>
                  <CardContent className="pt-6">
                    <Skeleton className="h-40 w-full" />
                  </CardContent>
                </Card>
              ))}
            </div>
          </PageContainer>
        </main>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 overflow-auto">
        <PageContainer>
          <Header title={PAGE_TITLES.settings} />
          <div className="grid gap-6 lg:grid-cols-2">
            <RiskParameters config={localConfig} onUpdate={handleUpdate} />
            <ScanSettings config={localConfig} onUpdate={handleUpdate} />
            <PlatformToggles config={localConfig} onUpdate={handleUpdate} />
            <TradeSyncSettings config={localConfig} onUpdate={handleUpdate} />
            <AutoTradeSettings config={localConfig} onUpdate={handleUpdate} />
            <NotificationSettings config={localConfig} onUpdate={handleUpdate} />
            <CostTracker />
            <ApiStatus />
          </div>
        </PageContainer>
      </main>
    </div>
  );
}
