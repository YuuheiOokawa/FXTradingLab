"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, ChevronDown, ChevronUp } from "lucide-react";

import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { formatPctPlain, formatPnl } from "@/lib/utils";
import type { Granularity, Instrument, WalkForwardResult } from "@/types/api";

interface WalkForwardFormValues {
  pair: string;
  timeframe: Granularity;
  candle_count: number;
  train_bars: number;
  test_bars: number;
}

const DEFAULTS: WalkForwardFormValues = {
  pair: "USD_JPY",
  timeframe: "M15",
  candle_count: 1200,
  train_bars: 400,
  test_bars: 120,
};

const TIMEFRAMES: Granularity[] = ["M15", "H1", "H4"];

function MetricCell({ value, format }: { value: number | null; format: (v: number) => string }) {
  return <span>{value == null ? "—" : format(value)}</span>;
}

export function WalkForwardPanel() {
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState<WalkForwardFormValues>(DEFAULTS);

  const { data: instruments } = useQuery<Instrument[]>({
    queryKey: ["instruments"],
    queryFn: () => api.get("/instruments"),
    staleTime: 60_000,
  });

  const mutation = useMutation<WalkForwardResult, ApiError, WalkForwardFormValues>({
    mutationFn: (body) => api.post<WalkForwardResult>("/backtests/walk-forward", body),
  });

  function set<K extends keyof WalkForwardFormValues>(key: K, value: WalkForwardFormValues[K]) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    mutation.mutate(values);
  }

  const result = mutation.data;

  return (
    <Card>
      <CardHeader>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-center justify-between text-left"
        >
          <div>
            <CardTitle>ウォークフォワード分析</CardTitle>
            <p className="mt-1 text-xs font-normal text-muted-foreground">
              学習期間ごとにパラメータ候補を選び、その直後の未使用（検証）期間だけで成績を測定します。過学習していないかを確認するための分析ツールです。
            </p>
          </div>
          {open ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        </button>
      </CardHeader>
      {open && (
        <CardContent className="space-y-6">
          <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-muted-foreground">通貨ペア</span>
              <Select value={values.pair} onChange={(e) => set("pair", e.target.value)}>
                {(instruments ?? []).map((inst) => (
                  <option key={inst.symbol} value={inst.symbol}>
                    {inst.symbol}
                  </option>
                ))}
                {!instruments?.length && <option value="USD_JPY">USD_JPY</option>}
              </Select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-muted-foreground">時間足</span>
              <Select value={values.timeframe} onChange={(e) => set("timeframe", e.target.value as Granularity)}>
                {TIMEFRAMES.map((tf) => (
                  <option key={tf} value={tf}>
                    {tf}
                  </option>
                ))}
              </Select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-muted-foreground">取得本数</span>
              <Input
                type="number"
                min={700}
                max={5000}
                step={100}
                value={values.candle_count}
                onChange={(e) => set("candle_count", Number(e.target.value))}
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-muted-foreground">学習期間(本)</span>
              <Input
                type="number"
                min={100}
                step={50}
                value={values.train_bars}
                onChange={(e) => set("train_bars", Number(e.target.value))}
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-muted-foreground">検証期間(本)</span>
              <Input
                type="number"
                min={30}
                step={10}
                value={values.test_bars}
                onChange={(e) => set("test_bars", Number(e.target.value))}
              />
            </label>
            <div className="col-span-full flex items-center gap-3">
              <Button type="submit" disabled={mutation.isPending}>
                {mutation.isPending ? "実行中…（数十秒かかる場合があります）" : "ウォークフォワード分析を実行"}
              </Button>
              <span className="text-xs text-muted-foreground">
                ウィンドウごとにパラメータの組み合わせを総当たりで検証するため、通常のバックテストより時間がかかります。
              </span>
            </div>
          </form>

          {mutation.isError && (
            <div className="flex items-center gap-2 rounded-lg border border-sell/30 bg-sell/10 p-4 text-sm text-sell">
              <AlertTriangle size={16} className="shrink-0" />
              <span>実行に失敗しました: {mutation.error instanceof ApiError ? mutation.error.message : "不明なエラー"}</span>
            </div>
          )}

          {result && (
            <div className="space-y-6">
              {result.overfitting_warning && (
                <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-500">
                  <AlertTriangle size={16} className="mt-0.5 shrink-0" />
                  <span>{result.overfitting_warning}</span>
                </div>
              )}
              <p className="rounded-lg border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
                {result.disclaimer}
              </p>

              <div>
                <h3 className="mb-2 text-sm font-semibold">
                  結合Out-of-Sample成績（全ウィンドウの検証期間のみを連結）
                </h3>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <div className="rounded-lg border border-border p-3">
                    <div className="text-xs text-muted-foreground">総損益</div>
                    <div className={result.combined_test_metrics.total_pnl >= 0 ? "text-buy" : "text-sell"}>
                      {formatPnl(result.combined_test_metrics.total_pnl)}
                    </div>
                  </div>
                  <div className="rounded-lg border border-border p-3">
                    <div className="text-xs text-muted-foreground">勝率</div>
                    <div>{formatPctPlain(result.combined_test_metrics.win_rate_pct, 1)}</div>
                  </div>
                  <div className="rounded-lg border border-border p-3">
                    <div className="text-xs text-muted-foreground">PF</div>
                    <div>{result.combined_test_metrics.profit_factor?.toFixed(2) ?? "—"}</div>
                  </div>
                  <div className="rounded-lg border border-border p-3">
                    <div className="text-xs text-muted-foreground">最大DD</div>
                    <div>{formatPctPlain(result.combined_test_metrics.max_drawdown_pct, 1)}</div>
                  </div>
                </div>
              </div>

              <div>
                <h3 className="mb-2 text-sm font-semibold">パラメータの安定性</h3>
                <div className="overflow-x-auto rounded-lg border border-border">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
                        <th className="px-3 py-2 font-medium">パラメータ</th>
                        <th className="px-3 py-2 font-medium">最頻値</th>
                        <th className="px-3 py-2 font-medium">一致率</th>
                        <th className="px-3 py-2 font-medium">安定性</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.parameter_stability.map((s) => (
                        <tr key={s.param} className="border-b border-border last:border-0">
                          <td className="px-3 py-2">{s.param}</td>
                          <td className="px-3 py-2">{s.most_common_value}</td>
                          <td className="px-3 py-2">{formatPctPlain(s.agreement_ratio * 100, 0)}</td>
                          <td className="px-3 py-2">
                            {s.is_stable ? (
                              <span className="text-buy">安定</span>
                            ) : (
                              <span className="text-amber-500">不安定</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div>
                <h3 className="mb-2 text-sm font-semibold">ウィンドウごとの結果（{result.windows.length}件）</h3>
                <div className="overflow-x-auto rounded-lg border border-border">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
                        <th className="px-3 py-2 font-medium">#</th>
                        <th className="px-3 py-2 font-medium">検証期間</th>
                        <th className="px-3 py-2 font-medium">選択パラメータ</th>
                        <th className="px-3 py-2 font-medium">学習損益</th>
                        <th className="px-3 py-2 font-medium">検証損益</th>
                        <th className="px-3 py-2 font-medium">検証PF</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.windows.map((w) => (
                        <tr key={w.window_index} className="border-b border-border last:border-0">
                          <td className="px-3 py-2">{w.window_index}</td>
                          <td className="px-3 py-2 text-xs text-muted-foreground">
                            {new Date(w.test_start).toLocaleDateString("ja-JP")} 〜{" "}
                            {new Date(w.test_end).toLocaleDateString("ja-JP")}
                          </td>
                          <td className="px-3 py-2 text-xs">
                            SL{w.chosen_params.stop_loss_pips} / TP{w.chosen_params.take_profit_pips} / スコア
                            {w.chosen_params.min_score_threshold}
                          </td>
                          <td className="px-3 py-2">
                            <MetricCell value={w.train_metrics.total_pnl} format={formatPnl} />
                          </td>
                          <td className="px-3 py-2">
                            <span className={w.test_metrics.total_pnl >= 0 ? "text-buy" : "text-sell"}>
                              {formatPnl(w.test_metrics.total_pnl)}
                            </span>
                          </td>
                          <td className="px-3 py-2">{w.test_metrics.profit_factor?.toFixed(2) ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
}
