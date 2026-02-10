import { LayoutDashboard, Search, BarChart3, Settings, TrendingUp } from "lucide-react";

import type { Platform, Confidence } from "@/lib/types";

export const SITE_CONFIG = {
  name: "AugurBot",
  description: "AI-powered prediction market edge detection",
  url: process.env.NEXT_PUBLIC_SITE_URL || "https://augurbot.com",
};

export const NAV_ITEMS = [
  { label: "Dashboard", href: "/", icon: LayoutDashboard },
  { label: "Markets", href: "/markets", icon: Search },
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
  min_volume: 10000,
  kelly_fraction: 0.33,
  max_single_bet_fraction: 0.05,
  re_estimate_trigger: 0.05,
  scan_interval_hours: 4,
  bankroll: 1000,
  platforms_enabled: {
    polymarket: true,
    kalshi: false,
    manifold: true,
    metaculus: false,
  },
};

export const EMPTY_STATES = {
  recommendations:
    "No active recommendations. Run a scan to discover high-EV opportunities.",
  markets:
    "No markets tracked yet. Trigger a scan to start fetching markets from prediction platforms.",
  performance:
    "No resolved markets yet. Performance data will appear once markets begin resolving.",
  estimates:
    "No AI estimates for this market. Click Refresh Estimate to generate one.",
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
  performance: "Performance & Calibration",
  settings: "Settings",
};

export { TrendingUp };
