import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatPercent(value: number, decimals = 1): string {
  return `${(value * 100).toFixed(decimals)}%`;
}

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatCompactNumber(value: number): string {
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

export function formatRelativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;

  // Future dates: show "in Xh", "in Xd", or the date
  if (diffMs < 0) {
    const futureDiffMs = -diffMs;
    const futureMinutes = Math.floor(futureDiffMs / 60_000);
    const futureHours = Math.floor(futureMinutes / 60);
    const futureDays = Math.floor(futureHours / 24);

    if (futureMinutes < 60) {
      return `in ${futureMinutes}m`;
    }
    if (futureHours < 24) {
      return `in ${futureHours}h`;
    }
    if (futureDays < 7) {
      return `in ${futureDays}d`;
    }
    const date = new Date(dateStr);
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }

  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSeconds < 60) {
    return "just now";
  }
  if (diffMinutes < 60) {
    return `${diffMinutes}m ago`;
  }
  if (diffHours < 24) {
    return `${diffHours}h ago`;
  }
  if (diffDays < 7) {
    return `${diffDays}d ago`;
  }

  const date = new Date(dateStr);
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function getEvColor(ev: number): string {
  if (ev > 0.10) return "var(--ev-positive)";
  if (ev > 0.05) return "var(--ev-moderate)";
  if (ev >= 0) return "var(--ev-neutral)";
  return "var(--ev-negative)";
}

export function getEvLabel(ev: number): string {
  if (ev > 0.10) return "Strong Edge";
  if (ev > 0.05) return "Moderate Edge";
  if (ev >= 0) return "Low Edge";
  return "No Edge";
}

export function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength).trimEnd() + "...";
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export function getKalshiMarketUrl(platformId: string): string {
  if (!platformId) return "https://kalshi.com/sports";
  // Kalshi's SPA accepts /markets/{ticker} and redirects to the event page
  return `https://kalshi.com/markets/${platformId.toLowerCase()}`;
}
