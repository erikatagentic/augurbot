import { Inbox } from "lucide-react";

export function EmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border px-8 py-16 text-center">
      <Inbox className="mb-4 h-10 w-10 text-foreground-subtle" />
      <h3 className="text-sm font-medium">{title}</h3>
      <p className="mt-1 text-sm text-foreground-muted">{description}</p>
    </div>
  );
}
