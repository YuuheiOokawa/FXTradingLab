"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type ForwardStats = {
  trades: number;
  wins: number;
  losses: number;
  win_rate_pct: number;
  total_pnl: number;
  expectancy: number;
  profit_factor: number | null;
  max_drawdown: number;
  avg_hold_hours: number | null;
  best: number;
  worst: number;
  verdict: string;
};

type PairRow = ForwardStats & {
  pair: string;
  vs_backtest: {
    backtest_win_rate_pct: number;
    backtest_profit_factor: number;
    win_rate_delta: number;
    profit_factor_delta: number | null;
    enough_trades: boolean;
  } | null;
};

type Report = {
  overall: ForwardStats;
  per_pair: PairRow[];
  min_trades_for_confidence: number;
  window_days: number | null;
  strategies: string[];
  exit_reasons: Record<string, number>;
};

const VERDICT: Record<string, { label: string; className: string }> = {
  no_trades: { label: "取引なし", className: "bg-muted text-muted-foreground" },
  too_early: { label: "判断は時期尚早", className: "bg-amber-500/15 text-amber-600 dark:text-amber-400" },
  tracking: { label: "想定どおり", className: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400" },
  marginal: { label: "ぎりぎり", className: "bg-amber-500/15 text-amber-600 dark:text-amber-400" },
  underperforming: { label: "想定を下回る", className: "bg-red-500/15 text-red-600 dark:text-red-400" },
};

function Verdict({ verdict }: { verdict: string }) {
  const v = VERDICT[verdict] ?? VERDICT.no_trades;
  return <span className={cn("rounded px-2 py-0.5 text-xs font-medium", v.className)}>{v.label}</span>;
}

function money(n: number) {
  return `${n >= 0 ? "+" : ""}${n.toLocaleString("ja-JP", { maximumFractionDigits: 0 })}`;
}

function Delta({ value, digits = 1 }: { value: number | null; digits?: number }) {
  if (value === null) return <span className="text-muted-foreground">—</span>;
  return (
    <span className={value >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}>
      {value >= 0 ? "+" : ""}
      {value.toFixed(digits)}
    </span>
  );
}

/**
 * Forward-test panel: how the playbook is doing on live paper trades versus
 * what its 23-year backtest predicted. Only auto-trader trades are counted
 * (the API filters on `strategy_code`), so a hand-placed order cannot flatter
 * or depress the strategy's record.
 */
export function ForwardTestPanel() {
  const { data, isLoading } = useQuery<Report>({
    queryKey: ["forward-test"],
    queryFn: () => api.get("/analytics/forward-test"),
    refetchInterval: 60_000,
  });

  if (isLoading) return <div className="text-sm text-muted-foreground">読み込み中...</div>;
  if (!data) return null;

  const o = data.overall;
  const noTrades = o.trades === 0;

  return (
    <div className="space-y-4">
      {noTrades && (
        <div className="rounded-md border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
          まだ自動売買の決済トレードがありません。Settings で <b>auto_mode を full_auto</b> にすると、
          通貨ごとのロジックが日足で判定を始めます。日足戦略なので、最初の記録が出るまで数日〜数週間かかります。
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { label: "決済トレード", value: `${o.trades}件`, sub: `勝ち${o.wins} / 負け${o.losses}` },
          { label: "勝率", value: `${o.win_rate_pct.toFixed(1)}%`, sub: `期待値 ${money(o.expectancy)}円/回` },
          {
            label: "プロフィットファクター",
            value: o.profit_factor === null ? "—" : o.profit_factor.toFixed(2),
            sub: o.profit_factor === null ? "負けトレードがまだ無い" : "1.0超で利益",
          },
          { label: "累計損益", value: `${money(o.total_pnl)}円`, sub: `最大DD ${money(o.max_drawdown)}円` },
        ].map((c) => (
          <Card key={c.label}>
            <CardHeader className="pb-2">
              <CardTitle>{c.label}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-semibold tabular-nums">{c.value}</div>
              <div className="mt-1 text-xs text-muted-foreground">{c.sub}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>通貨別：ライブ実績 vs バックテスト予想</CardTitle>
          <Verdict verdict={o.verdict} />
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
                <th className="py-2 pr-3 font-medium">通貨</th>
                <th className="py-2 pr-3 text-right font-medium">件数</th>
                <th className="py-2 pr-3 text-right font-medium">勝率</th>
                <th className="py-2 pr-3 text-right font-medium">想定比</th>
                <th className="py-2 pr-3 text-right font-medium">PF</th>
                <th className="py-2 pr-3 text-right font-medium">想定比</th>
                <th className="py-2 pr-3 text-right font-medium">損益</th>
                <th className="py-2 pr-3 text-right font-medium">平均保有</th>
                <th className="py-2 font-medium">判定</th>
              </tr>
            </thead>
            <tbody>
              {data.per_pair.length === 0 && (
                <tr>
                  <td colSpan={9} className="py-4 text-center text-muted-foreground">
                    データなし
                  </td>
                </tr>
              )}
              {data.per_pair.map((p) => (
                <tr key={p.pair} className="border-b border-border/60">
                  <td className="py-2 pr-3 font-medium">{p.pair}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{p.trades}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{p.win_rate_pct.toFixed(1)}%</td>
                  <td className="py-2 pr-3 text-right tabular-nums">
                    <Delta value={p.vs_backtest?.win_rate_delta ?? null} />
                  </td>
                  <td className="py-2 pr-3 text-right tabular-nums">
                    {p.profit_factor === null ? "—" : p.profit_factor.toFixed(2)}
                  </td>
                  <td className="py-2 pr-3 text-right tabular-nums">
                    <Delta value={p.vs_backtest?.profit_factor_delta ?? null} digits={2} />
                  </td>
                  <td
                    className={cn(
                      "py-2 pr-3 text-right tabular-nums",
                      p.total_pnl >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"
                    )}
                  >
                    {money(p.total_pnl)}
                  </td>
                  <td className="py-2 pr-3 text-right tabular-nums text-muted-foreground">
                    {p.avg_hold_hours === null ? "—" : `${(p.avg_hold_hours / 24).toFixed(1)}日`}
                  </td>
                  <td className="py-2">
                    <Verdict verdict={p.verdict} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-xs text-muted-foreground">
            「想定比」はバックテスト値との差。{data.min_trades_for_confidence}件未満は誤差の範囲なので
            「判断は時期尚早」と表示します。少ない件数の勝率で戦略を止めるのが、機能している戦略を捨てる
            典型的な失敗です。
          </p>
        </CardContent>
      </Card>

      {Object.keys(data.exit_reasons).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>決済理由の内訳</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {Object.entries(data.exit_reasons).map(([reason, count]) => (
                <span key={reason} className="rounded-md bg-muted px-2.5 py-1 text-xs">
                  {reason} <span className="font-medium tabular-nums">{count}</span>
                </span>
              ))}
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              「stop loss」が全く出ていない場合は、損切りが執行されていない可能性があります
              （以前は実際に未執行でした）。ここは必ず確認してください。
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
