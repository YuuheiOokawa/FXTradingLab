import { AlertTriangle, Wifi, WifiOff } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { StatTile } from "@/components/ui/stat-tile";
import type { SystemStatus } from "@/types/api";

const AUTO_MODE_LABEL: Record<SystemStatus["auto_mode"], string> = {
  manual: "MANUAL",
  semi_auto: "SEMI AUTO",
  full_auto: "FULL AUTO",
};

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}時間${m}分`;
  return `${m}分`;
}

function formatRelativeTime(iso: string | null): string {
  if (!iso) return "—";
  const deltaMs = Date.now() - new Date(iso).getTime();
  if (deltaMs < 0) return "たった今";
  const seconds = Math.floor(deltaMs / 1000);
  if (seconds < 60) return `${seconds}秒前`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}分前`;
  const hours = Math.floor(minutes / 60);
  return `${hours}時間前`;
}

function DependencyTile({ label, ok, detail }: { label: string; ok: boolean; detail?: string }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-border bg-card p-3">
      <div>
        <div className="text-xs text-muted-foreground">{label}</div>
        {detail && <div className="mt-0.5 text-xs text-muted-foreground">{detail}</div>}
      </div>
      <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${ok ? "bg-buy" : "bg-sell"}`} />
    </div>
  );
}

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
        <StatTile label="API稼働時間" value={formatUptime(status.api_uptime_seconds)} />
      </div>

      <div>
        <div className="mb-2 text-xs font-medium text-muted-foreground">依存コンポーネント</div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <DependencyTile label="Database" ok={status.database_connected} />
          <DependencyTile label="Redis" ok={status.redis_connected} />
          <DependencyTile
            label="Worker"
            ok={status.worker_alive}
            detail={status.worker_alive ? undefined : "30秒ごとのハートビートが途絶えています"}
          />
          <DependencyTile label="Market Stream" ok={status.broker_connected} />
          <DependencyTile label="Signal Engine" ok={status.signal_engine_ok} />
          <DependencyTile
            label="WebSocket Clients"
            ok={true}
            detail={`接続数: ${status.websocket_client_count}`}
          />
          <DependencyTile
            label="Last Price Update"
            ok={status.last_price_update != null}
            detail={formatRelativeTime(status.last_price_update)}
          />
          <DependencyTile
            label="Last Signal Generated"
            ok={status.last_signal_generated != null}
            detail={
              status.last_signal_generated
                ? `${formatRelativeTime(status.last_signal_generated.ts)} (score ${status.last_signal_generated.score})`
                : "まだシグナルが記録されていません"
            }
          />
        </div>
      </div>

      <div className="rounded-lg border border-border bg-card p-4">
        <div className="mb-2 text-xs font-medium text-muted-foreground">直近のエラー</div>
        {status.last_error ? (
          <div className="text-xs">
            <div className="flex items-center gap-2 text-sell">
              <AlertTriangle size={14} />
              <span className="font-medium">[{status.last_error.category}]</span>
              <span>{new Date(status.last_error.ts).toLocaleString("ja-JP")}</span>
            </div>
            <p className="mt-1 text-muted-foreground">{status.last_error.message}</p>
          </div>
        ) : (
          <span className="text-xs text-muted-foreground">エラーは記録されていません</span>
        )}
      </div>

      {status.providers_split && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-500">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <span>
            価格データ提供元（{status.market_data_provider.toUpperCase()}）と発注先ブローカー（
            {status.broker_provider.toUpperCase()}）が異なります。表示価格と約定価格にズレ（スプレッド・レイテンシ差）が生じる可能性があり、
            銘柄コードの対応関係も要確認です。
          </span>
        </div>
      )}

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
