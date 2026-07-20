"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Wifi, WifiOff } from "lucide-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { SystemStatus } from "@/types/api";

export function TopBar() {
  const { data } = useQuery<SystemStatus>({
    queryKey: ["system-status"],
    queryFn: () => api.get("/system/status"),
    refetchInterval: 5000,
  });

  return (
    <header className="flex h-14 items-center justify-between gap-4 border-b border-border bg-card/40 px-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span className="font-medium text-foreground">
          {data?.app_env === "production" ? "本番環境" : "開発環境"}
        </span>
        <span className="text-border">/</span>
        <span className="uppercase">{data?.broker_provider ?? "..."}</span>
        <span className="text-border">/</span>
        <span>{data?.broker_environment === "live" ? "LIVE口座" : "デモ/練習環境"}</span>
      </div>
      <div className="flex items-center gap-3">
        {data?.kill_switch_active && (
          <span className="flex items-center gap-1.5 rounded-md bg-destructive/15 px-2.5 py-1 text-xs font-semibold text-destructive">
            <AlertTriangle size={14} /> KILL SWITCH ACTIVE
          </span>
        )}
        <span
          className={cn(
            "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium",
            data?.broker_connected ? "bg-buy/15 text-buy" : "bg-sell/15 text-sell"
          )}
        >
          {data?.broker_connected ? <Wifi size={14} /> : <WifiOff size={14} />}
          {data?.broker_connected ? "Broker接続中" : "Broker未接続"}
        </span>
        <span className="rounded-md bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
          {data?.auto_mode === "full_auto" ? "FULL AUTO" : data?.auto_mode === "semi_auto" ? "SEMI AUTO" : "MANUAL"}
        </span>
      </div>
    </header>
  );
}
