import { cn } from "@/lib/utils";
import { MobileNav } from "./mobile-nav";

export function Header({
  title,
  description,
  actions,
  className,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mb-8 flex items-start justify-between gap-4", className)}>
      <div className="flex items-center gap-3">
        <MobileNav />
        <div>
          <h1 className="text-2xl font-semibold">{title}</h1>
        {description && (
          <p className="mt-1 text-sm text-foreground-muted">{description}</p>
        )}
        </div>
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}
