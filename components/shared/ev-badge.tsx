import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function EVBadge({ ev, size = "md" }: { ev: number; size?: "sm" | "md" }) {
  const config = getEvConfig(ev);

  return (
    <Badge
      variant="outline"
      className={cn(
        "font-medium",
        size === "sm" ? "text-xs px-1.5 py-0" : "text-xs px-2 py-0.5"
      )}
      style={{ borderColor: config.color, color: config.color }}
    >
      {config.label}
    </Badge>
  );
}

function getEvConfig(ev: number) {
  if (ev > 0.1) {
    return { label: "Strong Edge", color: "var(--ev-positive)" };
  }
  if (ev > 0.05) {
    return { label: "Moderate Edge", color: "var(--ev-moderate)" };
  }
  if (ev >= 0) {
    return { label: "Low Edge", color: "var(--ev-neutral)" };
  }
  return { label: "No Edge", color: "var(--ev-negative)" };
}
