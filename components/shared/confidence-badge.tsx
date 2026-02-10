import { Badge } from "@/components/ui/badge";
import type { Confidence } from "@/lib/types";

const CONFIDENCE_CONFIG: Record<Confidence, { label: string; color: string }> = {
  high: { label: "High Confidence", color: "var(--confidence-high)" },
  medium: { label: "Medium", color: "var(--confidence-medium)" },
  low: { label: "Low", color: "var(--confidence-low)" },
};

export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  const config = CONFIDENCE_CONFIG[confidence];

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
