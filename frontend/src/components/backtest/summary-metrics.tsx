import { StatTile } from "@/components/ui/stat-tile";
import { cn } from "@/lib/utils";
import { formatPct, formatPnl } from "@/lib/utils";
import type { BacktestSummary, BacktestSummaryMetrics } from "@/types/api";

export function OverallStatTiles({ metrics }: { metrics: BacktestSummaryMetrics }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      <StatTile label="総損益" value={formatPnl(metrics.total_pnl)} tone={metrics.total_pnl >= 0 ? "buy" : "sell"} />
      <StatTile label="リターン" value={formatPct(metrics.return_pct)} tone={metrics.return_pct >= 0 ? "buy" : "sell"} />
      <StatTile label="トレード数" value={metrics.trade_count} />
      <StatTile label="勝率" value={formatPct(metrics.win_rate_pct, 1)} />
      <StatTile label="平均利益" value={formatPnl(metrics.avg_win)} tone="buy" />
      <StatTile label="平均損失" value={formatPnl(metrics.avg_loss)} tone="sell" />
      <StatTile label="プロフィットファクター" value={metrics.profit_factor?.toFixed(2) ?? "—"} />
      <StatTile label="シャープレシオ" value={metrics.sharpe_ratio.toFixed(2)} />
      <StatTile label="最大ドローダウン" value={formatPct(metrics.max_drawdown_pct, 1)} tone="sell" />
      <StatTile label="最大連勝" value={metrics.max_consecutive_wins} tone="buy" />
      <StatTile label="最大連敗" value={metrics.max_consecutive_losses} tone="sell" />
    </div>
  );
}

const ROWS: { key: keyof BacktestSummaryMetrics; label: string; format: (v: number | null) => string; higherIsBetter: boolean }[] = [
  { key: "total_pnl", label: "総損益", format: (v) => formatPnl(v), higherIsBetter: true },
  { key: "return_pct", label: "リターン", format: (v) => formatPct(v), higherIsBetter: true },
  { key: "trade_count", label: "トレード数", format: (v) => `${v ?? 0}`, higherIsBetter: true },
  { key: "win_rate_pct", label: "勝率", format: (v) => formatPct(v, 1), higherIsBetter: true },
  { key: "profit_factor", label: "PF", format: (v) => (v == null ? "—" : v.toFixed(2)), higherIsBetter: true },
  { key: "sharpe_ratio", label: "シャープレシオ", format: (v) => (v == null ? "—" : v.toFixed(2)), higherIsBetter: true },
  { key: "max_drawdown_pct", label: "最大DD", format: (v) => formatPct(v, 1), higherIsBetter: false },
  { key: "max_consecutive_losses", label: "最大連敗", format: (v) => `${v ?? 0}`, higherIsBetter: false },
];

/** Side-by-side In-Sample vs Out-of-Sample comparison — the app's core
 * overfitting-prevention view: a strategy that looks great in-sample but
 * falls apart out-of-sample was overfit to the training window. */
export function SampleComparison({ summary }: { summary: BacktestSummary }) {
  const overfitWarning =
    summary.in_sample.win_rate_pct - summary.out_of_sample.win_rate_pct > 15 ||
    (summary.in_sample.profit_factor ?? 0) - (summary.out_of_sample.profit_factor ?? 0) > 0.5;

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold">In-Sample vs Out-of-Sample</h3>
        {overfitWarning && (
          <span className="rounded-md bg-amber-500/15 px-2 py-0.5 text-xs font-medium text-amber-500">
            OOS成績が大きく低下 — 過学習の可能性
          </span>
        )}
      </div>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
              <th className="px-3 py-2 font-medium">指標</th>
              <th className="px-3 py-2 font-medium">In-Sample</th>
              <th className="px-3 py-2 font-medium">Out-of-Sample</th>
              <th className="px-3 py-2 font-medium">差分</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map((row) => {
              const inVal = summary.in_sample[row.key] as number | null;
              const outVal = summary.out_of_sample[row.key] as number | null;
              const degraded =
                inVal != null && outVal != null && (row.higherIsBetter ? outVal < inVal : outVal > inVal);
              return (
                <tr key={row.key} className="border-b border-border last:border-0">
                  <td className="px-3 py-2 text-muted-foreground">{row.label}</td>
                  <td className="px-3 py-2 tabular-nums">{row.format(inVal)}</td>
                  <td className={cn("px-3 py-2 tabular-nums", degraded && "text-sell")}>{row.format(outVal)}</td>
                  <td className="px-3 py-2 tabular-nums text-muted-foreground">
                    {inVal != null && outVal != null ? row.format(outVal - inVal) : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
