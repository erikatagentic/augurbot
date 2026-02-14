"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Search, Wallet, BarChart3, Settings } from "lucide-react";
import { cn } from "@/lib/utils";

import type { LucideIcon } from "lucide-react";

interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: "/", icon: LayoutDashboard },
  { label: "Markets", href: "/markets", icon: Search },
  { label: "Trades", href: "/trades", icon: Wallet },
  { label: "Performance", href: "/performance", icon: BarChart3 },
  { label: "Settings", href: "/settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden w-64 shrink-0 border-r border-border bg-background lg:block">
      <div className="flex h-full flex-col">
        <div className="flex h-16 items-center border-b border-border px-6">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.svg" alt="AugurBot" className="h-8 w-8 rounded-lg" />
        </div>

        <nav className="flex-1 space-y-1 px-3 py-4">
          {NAV_ITEMS.map((item) => {
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);

            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-surface-raised text-foreground"
                    : "text-foreground-muted hover:bg-surface-raised hover:text-foreground"
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </aside>
  );
}
