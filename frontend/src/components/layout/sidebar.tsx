"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  LineChart,
  Radio,
  PlayCircle,
  FlaskConical,
  History,
  Wallet,
  ListChecks,
  BarChart3,
  Settings,
  Activity,
  Globe,
} from "lucide-react";

import { cn } from "@/lib/utils";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/markets", label: "Markets", icon: Globe },
  { href: "/chart", label: "Chart", icon: LineChart },
  { href: "/signals", label: "Signals", icon: Radio },
  { href: "/replay", label: "Replay", icon: PlayCircle },
  { href: "/simulation", label: "Simulation", icon: FlaskConical },
  { href: "/backtest", label: "Backtest", icon: History },
  { href: "/paper-trading", label: "Paper Trading", icon: Wallet },
  { href: "/trades", label: "Trades", icon: ListChecks },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: Settings },
  { href: "/system", label: "System", icon: Activity },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="hidden w-56 shrink-0 flex-col border-r border-border bg-card/40 md:flex">
      <div className="flex h-14 items-center gap-2 border-b border-border px-4">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground text-sm font-bold">
          FX
        </div>
        <span className="text-sm font-semibold">FX Trading Lab</span>
      </div>
      <nav className="flex-1 space-y-0.5 overflow-y-auto p-2">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname?.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                active ? "bg-primary/15 text-primary font-medium" : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <Icon size={16} />
              {label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
