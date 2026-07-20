"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";

import { api } from "@/lib/api";
import type { SystemStatus } from "@/types/api";

/**
 * Impossible-to-miss warning banner shown whenever LIVE trading's env-var gate
 * is on (docs/10_RISK_MANAGEMENT.md's first of three required conditions).
 * Even though live order submission always returns disabled today
 * (docs/14_IMPLEMENTATION_PLAN.md), the operator flipping this env var is
 * itself a meaningful state change worth surfacing loudly everywhere in the
 * app, not just on the Settings/System pages.
 */
export function LiveTradingBanner() {
  const { data } = useQuery<SystemStatus>({
    queryKey: ["system-status"],
    queryFn: () => api.get("/system/status"),
    refetchInterval: 5000,
  });

  if (!data?.live_trading_enabled_env) return null;

  return (
    <div className="flex items-center justify-center gap-2 bg-destructive px-4 py-2 text-sm font-bold text-destructive-foreground">
      <AlertTriangle size={16} />
      LIVE TRADING ENABLED — REAL MONEY CAN BE LOST — LIVE_TRADING_ENABLED=true
      {data.live_trading_admin_enabled && " かつ 管理者設定も有効です"}
    </div>
  );
}
