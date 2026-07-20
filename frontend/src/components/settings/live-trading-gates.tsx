"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, XCircle, AlertTriangle } from "lucide-react";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { RiskSettings } from "@/types/api";

interface LiveStatus {
  env_var_enabled: boolean;
  admin_setting_enabled: boolean;
  per_order_confirmation_required: boolean;
  ready: boolean;
}

function GateRow({ ok, label, note }: { ok: boolean; label: string; note: string }) {
  return (
    <div className="flex items-start gap-3 rounded-md border border-border p-3">
      {ok ? <CheckCircle2 size={18} className="mt-0.5 shrink-0 text-buy" /> : <XCircle size={18} className="mt-0.5 shrink-0 text-sell" />}
      <div>
        <div className="text-sm font-medium">{label}</div>
        <div className="text-xs text-muted-foreground">{note}</div>
      </div>
    </div>
  );
}

export function LiveTradingGates({ riskSettings }: { riskSettings: RiskSettings }) {
  const queryClient = useQueryClient();

  const { data: status, isLoading } = useQuery<LiveStatus>({
    queryKey: ["live-status"],
    queryFn: () => api.get("/live/status"),
    refetchInterval: 5000,
  });

  const toggleAdmin = useMutation<RiskSettings, Error, boolean>({
    mutationFn: (enabled) => api.put<RiskSettings>("/settings/risk", { live_trading_admin_enabled: enabled }),
    onSuccess: (data) => {
      queryClient.setQueryData(["risk-settings"], data);
      queryClient.invalidateQueries({ queryKey: ["live-status"] });
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-500">
        <AlertTriangle size={14} className="mt-0.5 shrink-0" />
        <span>
          LIVE取引は3つのゲートすべてが有効な場合のみ許可される設計です。ただし、本ビルドは実発注（本番ブローカーへの注文送信）を実装していません。すべてのゲートが揃っても発注は行われません。
        </span>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <GateRow
          ok={!!status?.env_var_enabled}
          label="① 環境変数 (LIVE_TRADING_ENABLED)"
          note="サーバー運用者のみが設定可能。この画面からは変更できません。"
        />
        <GateRow
          ok={!!status?.admin_setting_enabled}
          label="② 管理者設定 (live_trading_admin_enabled)"
          note="下のトグルでこの画面から変更できます。"
        />
        <GateRow
          ok={!!status?.per_order_confirmation_required}
          label="③ 注文ごとの確認"
          note="発注のたびに人による最終確認が必須（常時要求）。"
        />
      </div>

      <div
        className={cn(
          "flex items-center justify-between rounded-md border p-3",
          status?.ready ? "border-buy/30 bg-buy/10" : "border-border bg-muted/20"
        )}
      >
        <span className="text-sm font-medium">
          総合ステータス: {isLoading ? "確認中..." : status?.ready ? "LIVE取引の3ゲートが有効" : "LIVE取引は無効"}
        </span>
      </div>

      <div className="flex items-center justify-between rounded-md border border-border p-3">
        <div>
          <div className="text-sm font-medium">管理者設定: live_trading_admin_enabled</div>
          <div className="text-xs text-muted-foreground">
            現在: {riskSettings.live_trading_admin_enabled ? "有効" : "無効"}
          </div>
        </div>
        <Button
          type="button"
          variant={riskSettings.live_trading_admin_enabled ? "destructive" : "outline"}
          size="sm"
          disabled={toggleAdmin.isPending}
          onClick={() => toggleAdmin.mutate(!riskSettings.live_trading_admin_enabled)}
        >
          {riskSettings.live_trading_admin_enabled ? "無効化する" : "有効化する"}
        </Button>
      </div>
    </div>
  );
}
