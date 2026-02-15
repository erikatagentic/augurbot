const CATEGORY_CONFIG: Record<string, { label: string; color: string }> = {
  sports: { label: "Sports", color: "var(--ev-positive)" },
  economics: { label: "Econ", color: "var(--platform-kalshi)" },
};

export function CategoryBadge({ category }: { category: string | null | undefined }) {
  if (!category) return null;

  const config = CATEGORY_CONFIG[category.toLowerCase()] ?? {
    label: category,
    color: "var(--foreground-muted)",
  };

  return (
    <span
      className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider"
      style={{
        color: config.color,
        backgroundColor: `color-mix(in srgb, ${config.color} 15%, transparent)`,
      }}
    >
      {config.label}
    </span>
  );
}
