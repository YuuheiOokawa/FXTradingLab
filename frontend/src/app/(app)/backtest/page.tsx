"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";

import { api, ApiError } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BacktestForm, type BacktestFormValues } from "@/components/backtest/backtest-form";
import { BacktestResultsPanel } from "@/components/backtest/results-panel";
import { WalkForwardPanel } from "@/components/backtest/walk-forward-panel";
import type { BacktestResult } from "@/types/api";

export default function BacktestPage() {
  const [inSampleRatio, setInSampleRatio] = useState(0.7);

  const mutation = useMutation<BacktestResult, ApiError, BacktestFormValues>({
    mutationFn: (values) => api.post<BacktestResult>("/backtests", values),
  });

  function handleSubmit(values: BacktestFormValues) {
    setInSampleRatio(values.in_sample_ratio);
    mutation.mutate(values);
  }

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold">バックテスト</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          過去データで戦略を検証します。In-Sample（学習期間）とOut-of-Sample（検証期間）を分けて評価することで、過学習を防ぎます。
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>設定</CardTitle>
        </CardHeader>
        <CardContent>
          <BacktestForm onSubmit={handleSubmit} pending={mutation.isPending} />
        </CardContent>
      </Card>

      {mutation.isError && (
        <div className="flex items-center gap-2 rounded-lg border border-sell/30 bg-sell/10 p-4 text-sm text-sell">
          <AlertTriangle size={16} className="shrink-0" />
          <span>
            バックテストの実行に失敗しました: {mutation.error instanceof ApiError ? mutation.error.message : "不明なエラー"}
          </span>
        </div>
      )}

      {mutation.data && (
        <BacktestResultsPanel backtestId={mutation.data.id} result={mutation.data} inSampleRatio={inSampleRatio} />
      )}

      <WalkForwardPanel />
    </div>
  );
}
