import { StatTile } from "@/components/ui/stat-tile";
import { formatPnl } from "@/lib/utils";
import type { PaperAccount, PaperPosition } from "@/types/api";
import type { JournalStats } from "./metrics";

export function SummaryStats({
  account,
  positions,
  stats,
}: {
  account?: PaperAccount;
  positions?: PaperPosition[];
  stats: JournalStats;
}) {
  const positionCount = account?.open_position_count ?? positions?.length ?? 0;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
      <StatTile
        label="総資産"
        value={account ? `¥${Math.round(account.balance).toLocaleString("ja-JP")}` : "—"}
        sub={account ? `最高値: ¥${Math.round(account.high_water_mark).toLocaleString("ja-JP")}` : undefined}
      />
      <StatTile
        label="本日の損益"
        value={`${formatPnl(stats.todayPnl)}円`}
        tone={stats.todayPnl > 0 ? "buy" : stats.todayPnl < 0 ? "sell" : "default"}
      />
      <StatTile
        label="累計損益"
        value={`${formatPnl(stats.totalPnl)}円`}
        tone={stats.totalPnl > 0 ? "buy" : stats.totalPnl < 0 ? "sell" : "default"}
      />
      <StatTile label="現在ポジション" value={`${positionCount}件`} />
      <StatTile label="勝率" value={stats.winRatePct !== null ? `${stats.winRatePct.toFixed(1)}%` : "—"} />
      <StatTile
        label="Profit Factor"
        value={
          stats.profitFactor === null ? "—" : Number.isFinite(stats.profitFactor) ? stats.profitFactor.toFixed(2) : "∞"
        }
      />
      <StatTile
        label="最大ドローダウン"
        value={stats.maxDrawdownPct !== null ? `${stats.maxDrawdownPct.toFixed(1)}%` : "—"}
        sub={stats.maxDrawdown > 0 ? `¥${Math.round(stats.maxDrawdown).toLocaleString("ja-JP")}` : undefined}
        tone={stats.maxDrawdownPct ? "sell" : "default"}
      />
      <StatTile label="本日のトレード回数" value={`${stats.todayTradeCount}回`} />
    </div>
  );
}
