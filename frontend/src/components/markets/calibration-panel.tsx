"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Calibration = {
  instrument: string;
  bars: number;
  annual_vol_pct: number;
  variance_ratio_60: number | null;
  median_adx: number | null;
  trending_share_pct: number;
  drift_pct_per_year: number;
  character: "trending" | "mean_reverting" | "neutral";
  recommended_style: string;
  recommended_adx_min: number | null;
  recommended_adx_max: number | null;
  recommended_stop_atr: number;
  confidence: "low" | "medium" | "high";
  warnings: string[];
  rationale: string;
  next_step: string;
  current_playbook: {
    style: string;
    enabled: boolean;
    matches_recommendation: boolean;
    note: string;
  } | null;
};

const CHARACTER: Record<string, { label: string; className: string }> = {
  trending: { label: "トレンド型", className: "bg-sky-500/15 text-sky-600 dark:text-sky-400" },
  mean_reverting: { label: "平均回帰型", className: "bg-violet-500/15 text-violet-600 dark:text-violet-400" },
  neutral: { label: "中立（エッジ薄い）", className: "bg-muted text-muted-foreground" },
};

const STYLE_LABEL: Record<string, string> = {
  breakout_trail: "ブレイクアウト＋トレイリング",
  trend_filtered_trail: "トレンド追随（長期フィルタ付き）",
  bollinger_fade: "ボリンジャー逆張り",
  rsi_fade: "RSI逆張り",
};

const CONFIDENCE: Record<string, string> = { low: "低", medium: "中", high: "高" };

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-border/50 py-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="tabular-nums">{value}</span>
    </div>
  );
}

/**
 * Measures a pair's character from its own daily history and suggests which
 * strategy family to test on it — the analysis that produced the shipped
 * per-instrument playbook. Deliberately framed as a hypothesis: on USD/JPY and
 * GBP/JPY the statistic and the validated backtest disagree, so the UI shows
 * both rather than implying the recommendation is the answer.
 */
export function CalibrationPanel({ symbols }: { symbols: string[] }) {
  const [symbol, setSymbol] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery<Calibration>({
    queryKey: ["calibration", symbol],
    queryFn: () => api.get(`/instruments/${symbol}/calibration`),
    enabled: symbol !== null,
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {symbols.map((s) => (
          <Button
            key={s}
            type="button"
            size="sm"
            variant={symbol === s ? "default" : "outline"}
            onClick={() => setSymbol(s)}
          >
            {s}
          </Button>
        ))}
      </div>

      {symbol === null && (
        <p className="text-sm text-muted-foreground">
          通貨ペアを選ぶと、その値動きの「性格」を測定し、どの戦略ファミリーを試すべきか提案します。
        </p>
      )}

      {isLoading && <p className="text-sm text-muted-foreground">測定中...</p>}
      {error && (
        <p className="text-sm text-red-600 dark:text-red-400">
          測定できませんでした（日足の履歴が足りない可能性があります）。
        </p>
      )}

      {data && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <span
                className={cn(
                  "rounded px-2 py-0.5 text-xs font-medium",
                  CHARACTER[data.character]?.className ?? CHARACTER.neutral.className
                )}
              >
                {CHARACTER[data.character]?.label ?? data.character}
              </span>
              <span className="text-xs text-muted-foreground">
                信頼度: {CONFIDENCE[data.confidence]}（{data.bars}本）
              </span>
            </div>
            <Row label="分散比 VR(60)" value={data.variance_ratio_60?.toFixed(3) ?? "—"} />
            <Row label="年率ボラティリティ" value={`${data.annual_vol_pct.toFixed(1)}%`} />
            <Row label="ADX中央値" value={data.median_adx?.toFixed(1) ?? "—"} />
            <Row label="トレンド発生率 (ADX≥25)" value={`${data.trending_share_pct.toFixed(0)}%`} />
            <Row label="年間ドリフト" value={`${data.drift_pct_per_year >= 0 ? "+" : ""}${data.drift_pct_per_year.toFixed(1)}%`} />
          </div>

          <div className="space-y-3">
            <div className="rounded-md border border-border p-3">
              <div className="text-xs uppercase text-muted-foreground">推奨（＝まず試す候補）</div>
              <div className="mt-1 font-medium">
                {STYLE_LABEL[data.recommended_style] ?? data.recommended_style}
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                損切り {data.recommended_stop_atr}×ATR
                {data.recommended_adx_min !== null && ` / ADX ≥ ${data.recommended_adx_min}`}
                {data.recommended_adx_max !== null && ` / ADX ≤ ${data.recommended_adx_max}`}
              </div>
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{data.rationale}</p>
            </div>

            {data.current_playbook && (
              <div
                className={cn(
                  "rounded-md border p-3",
                  data.current_playbook.matches_recommendation
                    ? "border-border"
                    : "border-amber-500/40 bg-amber-500/5"
                )}
              >
                <div className="text-xs uppercase text-muted-foreground">現在の設定</div>
                <div className="mt-1 font-medium">
                  {STYLE_LABEL[data.current_playbook.style] ?? data.current_playbook.style}
                  {!data.current_playbook.enabled && (
                    <span className="ml-2 text-xs text-muted-foreground">（無効）</span>
                  )}
                </div>
                <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                  {data.current_playbook.note}
                </p>
              </div>
            )}

            {data.warnings.length > 0 && (
              <ul className="space-y-1 rounded-md bg-amber-500/10 p-3 text-xs leading-relaxed">
                {data.warnings.map((w) => (
                  <li key={w}>⚠️ {w}</li>
                ))}
              </ul>
            )}

            <p className="text-xs leading-relaxed text-muted-foreground">💡 {data.next_step}</p>
          </div>
        </div>
      )}
    </div>
  );
}
