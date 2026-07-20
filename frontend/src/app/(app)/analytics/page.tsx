"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { SignalOutcomeTable } from "@/components/analytics/signal-outcome-table";
import { WinRateChart } from "@/components/analytics/win-rate-chart";
import { WinRateTable } from "@/components/analytics/win-rate-table";
import type { WinRateBreakdown } from "@/types/api";

const DIMENSIONS: { key: string; label: string }[] = [
  { key: "hour", label: "時間帯" },
  { key: "weekday", label: "曜日" },
  { key: "pair", label: "通貨ペア" },
  { key: "direction", label: "方向" },
  { key: "regime", label: "相場レジーム" },
  { key: "score_bucket", label: "シグナルスコア帯" },
];

export default function AnalyticsPage() {
  const [dimension, setDimension] = useState("hour");
  const [metric, setMetric] = useState<"win_rate_pct" | "total_pnl">("win_rate_pct");

  const { data, isLoading } = useQuery<WinRateBreakdown>({
    queryKey: ["win-rate", dimension],
    queryFn: () => api.get(`/analytics/win-rate?dimension=${dimension}`),
  });

  const totalTrades = data?.breakdown.reduce((s, b) => s + b.trades, 0) ?? 0;

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold">分析</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          どの条件で実際に勝てているかを可視化します。決済済みトレード（バックテスト・Paper・デモ・LIVE）を集計します。
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>切り口</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {DIMENSIONS.map((d) => (
              <Button
                key={d.key}
                type="button"
                size="sm"
                variant={dimension === d.key ? "default" : "outline"}
                onClick={() => setDimension(d.key)}
              >
                {d.label}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      {isLoading && <div className="text-sm text-muted-foreground">読み込み中...</div>}

      {data && (
        <>
          <div className="text-xs text-muted-foreground">
            集計対象トレード数: {totalTrades} / 切り口: {DIMENSIONS.find((d) => d.key === dimension)?.label}
          </div>

          <Card>
            <CardHeader className="flex-row items-center justify-between space-y-0">
              <CardTitle>{metric === "win_rate_pct" ? "勝率" : "合計損益"}の内訳</CardTitle>
              <div className="flex gap-1">
                <button
                  type="button"
                  onClick={() => setMetric("win_rate_pct")}
                  className={cn(
                    "rounded-md px-2.5 py-1 text-xs font-medium",
                    metric === "win_rate_pct" ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
                  )}
                >
                  勝率
                </button>
                <button
                  type="button"
                  onClick={() => setMetric("total_pnl")}
                  className={cn(
                    "rounded-md px-2.5 py-1 text-xs font-medium",
                    metric === "total_pnl" ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
                  )}
                >
                  損益
                </button>
              </div>
            </CardHeader>
            <CardContent>
              <WinRateChart breakdown={data.breakdown} metric={metric} />
            </CardContent>
          </Card>

          <WinRateTable breakdown={data.breakdown} />
        </>
      )}

      <SignalOutcomeTable />
    </div>
  );
}
