"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";

import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EquityCurveChart } from "@/components/backtest/equity-curve-chart";
import { OverallStatTiles, SampleComparison } from "@/components/backtest/summary-metrics";
import { TradeList } from "@/components/backtest/trade-list";
import type { BacktestResult, BacktestTrade } from "@/types/api";

export function BacktestResultsPanel({
  backtestId,
  result,
  inSampleRatio,
  showPermalink = true,
}: {
  backtestId: string;
  result: BacktestResult;
  inSampleRatio: number;
  showPermalink?: boolean;
}) {
  const { data: trades, isLoading } = useQuery<BacktestTrade[]>({
    queryKey: ["backtest-trades", backtestId],
    queryFn: () => api.get(`/backtests/${backtestId}/trades`),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">結果</h2>
        {showPermalink && (
          <Link
            href={`/backtest/${backtestId}`}
            className="flex items-center gap-1 text-xs text-primary hover:underline"
          >
            結果ページを開く <ExternalLink size={12} />
          </Link>
        )}
      </div>

      <OverallStatTiles metrics={result.summary.overall} />

      <Card>
        <CardHeader>
          <CardTitle>エクイティカーブ</CardTitle>
        </CardHeader>
        <CardContent>
          <EquityCurveChart equityCurve={result.equity_curve} inSampleRatio={inSampleRatio} />
        </CardContent>
      </Card>

      <SampleComparison summary={result.summary} />

      <div>
        <h3 className="mb-2 text-sm font-semibold">トレード一覧 ({result.trade_count}件) — クリックで根拠を表示</h3>
        <TradeList trades={trades ?? []} isLoading={isLoading} />
      </div>
    </div>
  );
}
