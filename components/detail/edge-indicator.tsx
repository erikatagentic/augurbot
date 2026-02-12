import { formatPercent, getEvColor } from "@/lib/utils";

export function EdgeIndicator({
  edge,
  ev,
  outcomeLabel,
}: {
  edge: number;
  ev: number;
  outcomeLabel?: string | null;
}) {
  const absEdge = Math.abs(edge);
  const widthPercent = Math.min(absEdge / 0.3, 1) * 100;
  const color = getEvColor(ev);
  const direction = edge >= 0 ? "YES" : "NO";
  const label = outcomeLabel ? `Bet: ${outcomeLabel}` : direction;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-widest text-foreground-muted">
          Edge
        </span>
        <span className="text-sm font-medium tabular-nums" style={{ color }}>
          {edge > 0 ? "+" : ""}
          {formatPercent(edge)} ({label})
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-surface-raised">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${widthPercent}%`,
            backgroundColor: color,
          }}
        />
      </div>
    </div>
  );
}
