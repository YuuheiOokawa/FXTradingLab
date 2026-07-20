import { cn, formatPnl } from "@/lib/utils";
import type { WinRateBreakdown } from "@/types/api";

export function WinRateTable({ breakdown }: { breakdown: WinRateBreakdown["breakdown"] }) {
  if (!breakdown.length) {
    return <div className="p-4 text-sm text-muted-foreground">データがありません</div>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
            <th className="px-3 py-2 font-medium">条件</th>
            <th className="px-3 py-2 font-medium">トレード数</th>
            <th className="px-3 py-2 font-medium">勝率</th>
            <th className="px-3 py-2 font-medium">合計損益</th>
          </tr>
        </thead>
        <tbody>
          {breakdown
            .slice()
            .sort((a, b) => b.trades - a.trades)
            .map((b) => (
              <tr key={b.key} className="border-b border-border last:border-0">
                <td className="px-3 py-2 font-medium">{b.key}</td>
                <td className="px-3 py-2 tabular-nums">{b.trades}</td>
                <td className={cn("px-3 py-2 tabular-nums", b.win_rate_pct >= 50 ? "text-buy" : "text-sell")}>
                  {b.win_rate_pct.toFixed(1)}%
                </td>
                <td className={cn("px-3 py-2 tabular-nums font-medium", b.total_pnl >= 0 ? "text-buy" : "text-sell")}>
                  {formatPnl(b.total_pnl)}
                </td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}
