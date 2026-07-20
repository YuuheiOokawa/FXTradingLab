import { Badge } from "@/components/ui/badge";
import { cn, formatPnl, formatPrice } from "@/lib/utils";
import type { TradeJournalEntry } from "@/types/api";

const SOURCE_LABEL: Record<string, string> = {
  backtest: "バックテスト",
  paper: "Paper",
  demo: "デモ",
  live: "LIVE",
};

function formatTime(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ja-JP", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function TradesTable({ trades, isLoading }: { trades: TradeJournalEntry[]; isLoading?: boolean }) {
  if (isLoading) return <div className="p-4 text-sm text-muted-foreground">読み込み中...</div>;
  if (!trades.length) return <div className="p-4 text-sm text-muted-foreground">条件に一致するトレードがありません</div>;

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
            <th className="px-3 py-2 font-medium">ソース</th>
            <th className="px-3 py-2 font-medium">通貨ペア</th>
            <th className="px-3 py-2 font-medium">方向</th>
            <th className="px-3 py-2 font-medium">エントリー</th>
            <th className="px-3 py-2 font-medium">決済</th>
            <th className="px-3 py-2 font-medium">数量</th>
            <th className="px-3 py-2 font-medium">損益</th>
            <th className="px-3 py-2 font-medium">スコア</th>
            <th className="px-3 py-2 font-medium">レジーム</th>
            <th className="px-3 py-2 font-medium">理由</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr key={t.id} className="border-b border-border last:border-0 hover:bg-muted/20">
              <td className="px-3 py-2">
                <Badge variant={t.source === "live" ? "warning" : "outline"}>{SOURCE_LABEL[t.source] ?? t.source}</Badge>
              </td>
              <td className="px-3 py-2 font-medium">{t.pair}</td>
              <td className="px-3 py-2">
                <Badge variant={t.direction === "BUY" ? "buy" : "sell"}>{t.direction}</Badge>
              </td>
              <td className="px-3 py-2 tabular-nums">
                {formatPrice(t.entry_price)}
                <div className="text-xs text-muted-foreground">{formatTime(t.entry_time)}</div>
              </td>
              <td className="px-3 py-2 tabular-nums">
                {formatPrice(t.exit_price)}
                <div className="text-xs text-muted-foreground">{formatTime(t.exit_time)}</div>
              </td>
              <td className="px-3 py-2 tabular-nums">{t.size.toLocaleString("ja-JP", { maximumFractionDigits: 0 })}</td>
              <td className={cn("px-3 py-2 tabular-nums font-medium", t.pnl >= 0 ? "text-buy" : "text-sell")}>
                {formatPnl(t.pnl)}
              </td>
              <td className="px-3 py-2 tabular-nums text-muted-foreground">{t.signal_score ?? "—"}</td>
              <td className="px-3 py-2 text-xs text-muted-foreground">{t.market_regime ?? "—"}</td>
              <td className="px-3 py-2 max-w-[220px] truncate text-xs text-muted-foreground" title={t.reason}>
                {t.reason}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
