import { LayoutDashboard, Search, Wallet, BarChart3, Settings, TrendingUp } from "lucide-react";

import type { Platform, Confidence } from "@/lib/types";

export const SITE_CONFIG = {
  name: "AugurBot",
  description: "AI-powered prediction market edge detection",
  url: process.env.NEXT_PUBLIC_SITE_URL || "https://augurbot.com",
};

export const NAV_ITEMS = [
  { label: "Dashboard", href: "/", icon: LayoutDashboard },
  { label: "Markets", href: "/markets", icon: Search },
  { label: "Trades", href: "/trades", icon: Wallet },
  { label: "Performance", href: "/performance", icon: BarChart3 },
  { label: "Settings", href: "/settings", icon: Settings },
] as const;

export const PLATFORM_CONFIG: Record<
  Platform,
  { label: string; colorVar: string; colorHex: string }
> = {
  polymarket: {
    label: "Polymarket",
    colorVar: "var(--platform-polymarket)",
    colorHex: "#A78BFA",
  },
  kalshi: {
    label: "Kalshi",
    colorVar: "var(--platform-kalshi)",
    colorHex: "#3B82F6",
  },
  manifold: {
    label: "Manifold",
    colorVar: "var(--platform-manifold)",
    colorHex: "#34D399",
  },
  metaculus: {
    label: "Metaculus",
    colorVar: "var(--platform-metaculus)",
    colorHex: "#FBBF24",
  },
};

export const CONFIDENCE_CONFIG: Record<
  Confidence,
  { label: string; colorVar: string }
> = {
  high: { label: "High Confidence", colorVar: "var(--confidence-high)" },
  medium: { label: "Medium", colorVar: "var(--confidence-medium)" },
  low: { label: "Low", colorVar: "var(--confidence-low)" },
};

export const EV_THRESHOLDS = {
  strong: 0.10,
  moderate: 0.05,
};

export const DEFAULT_CONFIG = {
  min_edge_threshold: 0.05,
  min_volume: 50000,
  kelly_fraction: 0.33,
  max_single_bet_fraction: 0.05,
  max_exposure_fraction: 0.25,
  max_event_exposure_fraction: 0.10,
  re_estimate_trigger: 0.05,
  scan_interval_hours: 24,
  bankroll: 1000,
  platforms_enabled: {
    polymarket: false,
    kalshi: true,
    manifold: false,
    metaculus: false,
  },
  markets_per_platform: 25,
  web_search_max_uses: 3,
  price_check_enabled: false,
  price_check_interval_hours: 6,
  estimate_cache_hours: 20,
  resolution_check_enabled: true,
  resolution_check_interval_hours: 6,
  trade_sync_enabled: false,
  trade_sync_interval_hours: 4,
  polymarket_wallet_address: "",
  kalshi_rsa_configured: false,
  auto_trade_enabled: false,
  auto_trade_min_ev: 0.05,
  max_close_hours: 24,
  notifications_enabled: false,
  notification_email: "",
  notification_slack_webhook: "",
  notification_min_ev: 0.08,
  daily_digest_enabled: true,
  scan_times: [8],
  use_premium_model: false,
  categories_enabled: { sports: true, economics: true },
};

export const EMPTY_STATES = {
  recommendations:
    "No active recommendations. Run a scan to discover high-EV Kalshi markets.",
  markets:
    "No markets tracked yet. Trigger a scan to start fetching Kalshi markets.",
  performance:
    "No resolved markets yet. Performance data will appear once markets begin resolving.",
  estimates:
    "No AI estimates for this market. Click Refresh Estimate to generate one.",
  trades:
    "No trades logged yet. Place a trade on Kalshi and log it here to track your performance.",
  openPositions:
    "No open positions. Log a trade to start tracking your portfolio.",
};

export const MARKET_TABLE_COLUMNS = [
  { key: "question", label: "Question" },
  { key: "platform", label: "Platform" },
  { key: "market_price", label: "Market Price" },
  { key: "ai_probability", label: "AI Estimate" },
  { key: "edge", label: "Edge" },
  { key: "ev", label: "EV" },
  { key: "confidence", label: "Confidence" },
] as const;

export const PAGE_TITLES = {
  dashboard: "Dashboard",
  markets: "Market Explorer",
  marketDetail: "Market Detail",
  trades: "Trades & Portfolio",
  performance: "Performance & Calibration",
  settings: "Settings",
};

export { TrendingUp };
