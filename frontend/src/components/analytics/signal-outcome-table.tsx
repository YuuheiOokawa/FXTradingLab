"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatPctPlain } from "@/lib/utils";
import type { SignalOutcomeResponse } from "@/types/api";

function cell(value: number | null, suffix = ""): string {
  return value == null ? "—" : `${value}${suffix}`;
}

export function SignalOutcomeTable() {
  const { data, isLoading } = useQuery<SignalOutcomeResponse>({
    queryKey: ["signal-outcomes"],
    queryFn: () => api.get("/analytics/signal-outcomes"),
  });

  const totalPending = data?.breakdown.reduce((s, b) => s + b.pending_outcome_count, 0) ?? 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>シグナル成績（スコア帯別）</CardTitle>
        <p className="mt-1 text-xs font-normal text-muted-foreground">
          シグナル発生から一定時間後（4時間）に価格がどう動いたかを集計します。実際にトレードしたかどうかに関わらず、シグナルの質そのものを見るための統計です。バックテスト/Paper
          Tradingのような同一足内のSL/TP優先順位は考慮していない、簡易的な指標です。
        </p>
      </CardHeader>
      <CardContent>
        {isLoading && <div className="text-sm text-muted-foreground">読み込み中...</div>}
        {data && (
          <>
            {totalPending > 0 && (
              <p className="mb-3 text-xs text-muted-foreground">
                集計待ち（発生から4時間経過していない、または候補足データが不足）: {totalPending}件
              </p>
            )}
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
                    <th className="px-3 py-2 font-medium">スコア帯</th>
                    <th className="px-3 py-2 font-medium">シグナル数</th>
                    <th className="px-3 py-2 font-medium">集計済</th>
                    <th className="px-3 py-2 font-medium">順行勝率</th>
                    <th className="px-3 py-2 font-medium">平均順行pips</th>
                    <th className="px-3 py-2 font-medium">平均逆行pips</th>
                    <th className="px-3 py-2 font-medium">4h後の平均pips</th>
                    <th className="px-3 py-2 font-medium">TP到達率</th>
                    <th className="px-3 py-2 font-medium">SL到達率</th>
                  </tr>
                </thead>
                <tbody>
                  {data.breakdown.map((b) => (
                    <tr key={b.score_bucket} className="border-b border-border last:border-0">
                      <td className="px-3 py-2 font-medium">{b.score_bucket}</td>
                      <td className="px-3 py-2">{b.signal_count}</td>
                      <td className="px-3 py-2">{b.outcome_count}</td>
                      <td className="px-3 py-2">
                        {b.favorable_move_win_rate_pct == null ? "—" : formatPctPlain(b.favorable_move_win_rate_pct, 1)}
                      </td>
                      <td className="px-3 py-2 text-buy">{cell(b.avg_max_favorable_pips)}</td>
                      <td className="px-3 py-2 text-sell">{cell(b.avg_max_adverse_pips)}</td>
                      <td className="px-3 py-2">{cell(b.avg_price_after_horizon_pips)}</td>
                      <td className="px-3 py-2">
                        {b.tp_reached_rate_pct == null ? "—" : formatPctPlain(b.tp_reached_rate_pct, 1)}
                      </td>
                      <td className="px-3 py-2">
                        {b.sl_reached_rate_pct == null ? "—" : formatPctPlain(b.sl_reached_rate_pct, 1)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
