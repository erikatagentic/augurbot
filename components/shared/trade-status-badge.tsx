import { Badge } from "@/components/ui/badge";

import type { TradeStatus } from "@/lib/types";

const STATUS_CONFIG: Record<TradeStatus, { label: string; color: string }> = {
  open: { label: "Open", color: "var(--ev-moderate)" },
  closed: { label: "Closed", color: "var(--foreground-muted)" },
  cancelled: { label: "Cancelled", color: "var(--ev-negative)" },
};

export function TradeStatusBadge({ status }: { status: TradeStatus }) {
  const config = STATUS_CONFIG[status] ?? {
    label: status,
    color: "var(--foreground-muted)",
  };

  return (
    <Badge
      variant="outline"
      className="text-xs px-2 py-0.5 font-medium"
      style={{ borderColor: config.color, color: config.color }}
    >
      {config.label}
    </Badge>
  );
}
