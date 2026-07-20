"use client";

import { use } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";

import { api } from "@/lib/api";
import { BacktestResultsPanel } from "@/components/backtest/results-panel";
import type { BacktestResult, Granularity } from "@/types/api";

interface BacktestDetail extends BacktestResult {
  config: {
    pair: string;
    timeframe: Granularity;
    in_sample_ratio: number;
    [key: string]: unknown;
  };
  status: string;
  created_at: string;
}

export default function BacktestDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const { data, isLoading, isError } = useQuery<BacktestDetail>({
    queryKey: ["backtest", id],
    queryFn: () => api.get(`/backtests/${id}`),
  });

  return (
    <div className="space-y-6 p-6">
      <Link href="/backtest" className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft size={14} /> バックテストへ戻る
      </Link>

      {isLoading && <div className="text-sm text-muted-foreground">読み込み中...</div>}
      {isError && <div className="text-sm text-sell">バックテスト結果が見つかりませんでした。</div>}

      {data && (
        <>
          <div>
            <h1 className="text-xl font-semibold">
              {data.config.pair} / {data.config.timeframe} バックテスト結果
            </h1>
            <p className="mt-1 text-xs text-muted-foreground">
              実行日時: {new Date(data.created_at).toLocaleString("ja-JP")} / ステータス: {data.status} / ID: {data.id}
            </p>
          </div>
          <BacktestResultsPanel
            backtestId={data.id}
            result={data}
            inSampleRatio={data.config.in_sample_ratio}
            showPermalink={false}
          />
        </>
      )}
    </div>
  );
}
