import { cn } from "@/lib/utils";
import type { SystemStatus } from "@/types/api";

export function SystemPanel({ status }: { status?: SystemStatus }) {
  if (!status) {
    return <p className="text-sm text-muted-foreground">読み込み中...</p>;
  }

  const liveEnabled = status.live_trading_admin_enabled && status.live_trading_enabled_env;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      <InfoTile label="Broker" value={status.broker_provider.toUpperCase()} />
      <InfoTile label="環境" value={status.broker_environment === "live" ? "本番" : "デモ/練習"} />
      <InfoTile
        label="Broker接続"
        value={status.broker_connected ? "接続中" : "未接続"}
        tone={status.broker_connected ? "buy" : "sell"}
      />
      <InfoTile
        label="Kill Switch"
        value={status.kill_switch_active ? "作動中" : "解除"}
        tone={status.kill_switch_active ? "sell" : "buy"}
      />
      <InfoTile
        label="自動売買モード"
        value={
          status.auto_mode === "full_auto" ? "フルオート" : status.auto_mode === "semi_auto" ? "セミオート" : "手動"
        }
      />
      <InfoTile label="実運用取引" value={liveEnabled ? "有効" : "無効"} tone={liveEnabled ? "sell" : "muted"} />
    </div>
  );
}

function InfoTile({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "buy" | "sell" | "muted";
}) {
  return (
    <div className="rounded-md border border-border bg-background/40 p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div
        className={cn(
          "mt-1 text-sm font-semibold text-foreground",
          tone === "buy" && "text-buy",
          tone === "sell" && "text-sell",
          tone === "muted" && "text-muted-foreground"
        )}
      >
        {value}
      </div>
    </div>
  );
}
