import { Wifi, WifiOff } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { StatTile } from "@/components/ui/stat-tile";
import type { SystemStatus } from "@/types/api";

const AUTO_MODE_LABEL: Record<SystemStatus["auto_mode"], string> = {
  manual: "MANUAL",
  semi_auto: "SEMI AUTO",
  full_auto: "FULL AUTO",
};

export function StatusOverview({ status }: { status: SystemStatus }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile
          label="ブローカー接続"
          value={
            <span className="flex items-center gap-1.5">
              {status.broker_connected ? <Wifi size={16} className="text-buy" /> : <WifiOff size={16} className="text-sell" />}
              {status.broker_connected ? "接続中" : "未接続"}
            </span>
          }
          tone={status.broker_connected ? "buy" : "sell"}
        />
        <StatTile label="プロバイダー" value={status.broker_provider.toUpperCase()} />
        <StatTile label="環境" value={status.broker_environment === "live" ? "LIVE" : "Practice"} />
        <StatTile label="動作モード" value={AUTO_MODE_LABEL[status.auto_mode]} />
      </div>

      <div className="rounded-lg border border-border bg-card p-4">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-medium text-muted-foreground">アプリ環境</span>
          <Badge variant={status.app_env === "production" ? "warning" : "outline"}>{status.app_env}</Badge>
        </div>
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">LIVE取引 (環境変数)</span>
          <Badge variant={status.live_trading_enabled_env ? "buy" : "muted"}>
            {status.live_trading_enabled_env ? "有効" : "無効"}
          </Badge>
        </div>
        <div className="mt-1.5 flex items-center justify-between text-xs">
          <span className="text-muted-foreground">LIVE取引 (管理者設定)</span>
          <Badge variant={status.live_trading_admin_enabled ? "buy" : "muted"}>
            {status.live_trading_admin_enabled ? "有効" : "無効"}
          </Badge>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-card p-4">
        <div className="mb-2 text-xs font-medium text-muted-foreground">監視銘柄 (Watchlist)</div>
        <div className="flex flex-wrap gap-1.5">
          {status.watchlist.map((symbol) => (
            <Badge key={symbol} variant="outline">
              {symbol}
            </Badge>
          ))}
          {!status.watchlist.length && <span className="text-xs text-muted-foreground">監視銘柄がありません</span>}
        </div>
      </div>
    </div>
  );
}
