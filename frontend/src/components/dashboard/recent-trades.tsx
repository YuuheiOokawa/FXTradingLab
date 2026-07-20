import { Badge } from "@/components/ui/badge";
import { cn, formatPnl, formatPrice } from "@/lib/utils";
import type { TradeJournalEntry } from "@/types/api";

export function RecentTrades({ trades }: { trades: TradeJournalEntry[] }) {
  if (trades.length === 0) {
    return <p className="text-sm text-muted-foreground">まだ取引履歴がありません。</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-muted-foreground">
            <th className="py-2 pr-4 font-medium">通貨ペア</th>
            <th className="py-2 pr-4 font-medium">方向</th>
            <th className="py-2 pr-4 font-medium">エントリー</th>
            <th className="py-2 pr-4 font-medium">決済</th>
            <th className="py-2 pr-4 font-medium">損益</th>
            <th className="py-2 pr-4 font-medium">ソース</th>
            <th className="py-2 font-medium">決済日時</th>
          </tr>
        </thead>
        <tbody>
          {trades.slice(0, 10).map((t) => (
            <tr key={t.id} className="border-b border-border/60 last:border-0">
              <td className="py-2 pr-4 font-medium text-foreground">{t.pair}</td>
              <td className="py-2 pr-4">
                <Badge variant={t.direction === "BUY" ? "buy" : "sell"}>
                  {t.direction === "BUY" ? "買い" : "売り"}
                </Badge>
              </td>
              <td className="py-2 pr-4 tabular-nums text-muted-foreground">{formatPrice(t.entry_price, 3)}</td>
              <td className="py-2 pr-4 tabular-nums text-muted-foreground">{formatPrice(t.exit_price, 3)}</td>
              <td
                className={cn(
                  "py-2 pr-4 tabular-nums font-medium",
                  t.pnl > 0 ? "text-buy" : t.pnl < 0 ? "text-sell" : "text-muted-foreground"
                )}
              >
                {formatPnl(t.pnl)}
              </td>
              <td className="py-2 pr-4 text-xs uppercase text-muted-foreground">{t.source}</td>
              <td className="py-2 text-xs text-muted-foreground">{new Date(t.closed_at).toLocaleString("ja-JP")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
