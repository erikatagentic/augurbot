import type { Platform } from "@/lib/types";

const PLATFORM_CONFIG: Record<Platform, { label: string; color: string }> = {
  polymarket: { label: "Polymarket", color: "var(--platform-polymarket)" },
  kalshi: { label: "Kalshi", color: "var(--platform-kalshi)" },
  manifold: { label: "Manifold", color: "var(--platform-manifold)" },
  metaculus: { label: "Metaculus", color: "var(--platform-metaculus)" },
};

export function PlatformBadge({ platform }: { platform: Platform }) {
  const config = PLATFORM_CONFIG[platform] ?? {
    label: platform,
    color: "var(--foreground-muted)",
  };

  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium">
      <span
        className="h-2 w-2 rounded-full"
        style={{ backgroundColor: config.color }}
      />
      {config.label}
    </span>
  );
}
