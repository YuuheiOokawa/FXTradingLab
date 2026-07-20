"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertOctagon, ShieldAlert } from "lucide-react";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { SystemStatus } from "@/types/api";

interface KillSwitchResponse {
  kill_switch_active: boolean;
  flattened_positions?: string[];
}

export function KillSwitch({ status }: { status: SystemStatus }) {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [flatten, setFlatten] = useState(true);
  const [lastFlattened, setLastFlattened] = useState<string[] | null>(null);

  const mutation = useMutation<KillSwitchResponse, Error, boolean>({
    mutationFn: (activate) => api.post<KillSwitchResponse>("/live/kill-switch", { activate, flatten_positions: flatten }),
    onSuccess: (data) => {
      queryClient.setQueryData<SystemStatus | undefined>(["system-status"], (prev) =>
        prev ? { ...prev, kill_switch_active: data.kill_switch_active } : prev
      );
      queryClient.invalidateQueries({ queryKey: ["system-status"] });
      queryClient.invalidateQueries({ queryKey: ["paper-positions"] });
      setLastFlattened(data.flattened_positions ?? null);
      setConfirming(false);
    },
  });

  const active = status.kill_switch_active;

  return (
    <div
      className={cn(
        "rounded-lg border-2 p-5",
        active ? "border-sell bg-sell/10" : "border-border bg-card"
      )}
    >
      <div className="flex items-center gap-2">
        <AlertOctagon size={20} className={active ? "text-sell" : "text-muted-foreground"} />
        <h3 className="text-base font-semibold">Kill Switch（緊急停止）</h3>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        有効化すると新規発注が即座に停止されます。「保有ポジションを全決済」を選ぶと、有効化と同時にすべての建玉をクローズします。
      </p>

      <div className="mt-4 flex items-center gap-2">
        <span
          className={cn(
            "rounded-md px-2.5 py-1 text-xs font-semibold",
            active ? "bg-sell text-sell-foreground" : "bg-buy/15 text-buy"
          )}
        >
          現在の状態: {active ? "有効 (取引停止中)" : "無効 (通常稼働)"}
        </span>
      </div>

      {!active && (
        <label className="mt-4 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={flatten}
            onChange={(e) => setFlatten(e.target.checked)}
            className="h-4 w-4 rounded border-border"
          />
          有効化と同時に保有ポジションを全決済する
        </label>
      )}

      <div className="mt-4">
        {!active && !confirming && (
          <Button type="button" variant="destructive" onClick={() => setConfirming(true)}>
            <ShieldAlert size={16} /> Kill Switchを有効化
          </Button>
        )}
        {!active && confirming && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-sell">本当に停止しますか？（{flatten ? "全ポジション決済あり" : "決済なし"}）</span>
            <Button type="button" variant="destructive" disabled={mutation.isPending} onClick={() => mutation.mutate(true)}>
              {mutation.isPending ? "実行中..." : "はい、停止する"}
            </Button>
            <Button type="button" variant="outline" onClick={() => setConfirming(false)}>
              キャンセル
            </Button>
          </div>
        )}
        {active && (
          <Button type="button" variant="outline" disabled={mutation.isPending} onClick={() => mutation.mutate(false)}>
            {mutation.isPending ? "解除中..." : "Kill Switchを解除"}
          </Button>
        )}
      </div>

      {lastFlattened && (
        <p className="mt-3 text-xs text-muted-foreground">
          {lastFlattened.length > 0 ? `決済されたポジション: ${lastFlattened.length}件` : "決済対象のポジションはありませんでした"}
        </p>
      )}
      {mutation.isError && <p className="mt-3 text-xs text-sell">操作に失敗しました。再度お試しください。</p>}
    </div>
  );
}
