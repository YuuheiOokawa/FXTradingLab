"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Wifi, WifiOff } from "lucide-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { MobileNav } from "@/components/layout/mobile-nav";
import type { SystemStatus } from "@/types/api";

export function TopBar() {
  const { data } = useQuery<SystemStatus>({
    queryKey: ["system-status"],
    queryFn: () => api.get("/system/status"),
    refetchInterval: 5000,
  });

  return (
    <header className="flex h-14 items-center justify-between gap-2 border-b border-border bg-card/40 px-3 md:gap-4 md:px-4">
      <div className="flex min-w-0 items-center gap-2">
        <MobileNav />
        <div className="flex min-w-0 items-center gap-2 truncate text-xs text-muted-foreground sm:text-sm">
          <span className="truncate font-medium text-foreground">
            {data?.app_env === "production" ? "本番環境" : "開発環境"}
          </span>
          <span className="hidden text-border sm:inline">/</span>
          <span className="hidden uppercase sm:inline">{data?.broker_provider ?? "..."}</span>
          <span className="hidden text-border sm:inline">/</span>
          <span className="hidden sm:inline">{data?.broker_environment === "live" ? "LIVE口座" : "デモ/練習環境"}</span>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-1.5 md:gap-3">
        {data?.kill_switch_active && (
          <span className="flex items-center gap-1.5 rounded-md bg-destructive/15 px-2.5 py-1 text-xs font-semibold text-destructive">
            <AlertTriangle size={14} /> KILL SWITCH ACTIVE
          </span>
        )}
        <span
          className={cn(
            "flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium sm:px-2.5",
            data?.broker_connected ? "bg-buy/15 text-buy" : "bg-sell/15 text-sell"
          )}
        >
          {data?.broker_connected ? <Wifi size={14} /> : <WifiOff size={14} />}
          <span className="hidden sm:inline">{data?.broker_connected ? "Broker接続中" : "Broker未接続"}</span>
        </span>
        <span className="hidden rounded-md bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground sm:inline-block">
          {data?.auto_mode === "full_auto" ? "FULL AUTO" : data?.auto_mode === "semi_auto" ? "SEMI AUTO" : "MANUAL"}
        </span>
      </div>
    </header>
  );
}
