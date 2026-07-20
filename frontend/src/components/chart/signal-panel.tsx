"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SignalBadge } from "@/components/signal-badge";
import { cn } from "@/lib/utils";
import type { ApiError } from "@/lib/api";
import type { SignalResponse } from "@/types/api";

const TREND_LABEL: Record<string, string> = {
  UPTREND: "上昇トレンド",
  DOWNTREND: "下降トレンド",
  RANGE: "レンジ",
  UNKNOWN: "不明",
};

const VOLATILITY_LABEL: Record<string, string> = {
  HIGH_VOLATILITY: "高ボラティリティ",
  LOW_VOLATILITY: "低ボラティリティ",
  NORMAL: "通常",
};

function ReasonIcon({ status }: { status: "met" | "partial" | "failed" }) {
  if (status === "met") return <span className="text-buy">✓</span>;
  if (status === "partial") return <span className="text-amber-500">△</span>;
  return <span className="text-muted-foreground">✗</span>;
}

export function SignalPanel({
  signal,
  isLoading,
  error,
}: {
  signal: SignalResponse | null | undefined;
  isLoading: boolean;
  error: unknown;
}) {
  return (
    <Card className="h-fit">
      <CardHeader>
        <CardTitle>シグナル判定</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {isLoading && !signal && <p className="text-sm text-muted-foreground">読み込み中...</p>}
        {!!error && (
          <p className="text-sm text-destructive">
            シグナルの取得に失敗しました{(error as ApiError)?.message ? `: ${(error as ApiError).message}` : ""}
          </p>
        )}
        {signal && (
          <>
            <div className="flex items-center justify-between">
              <SignalBadge label={signal.label} className="text-base" />
              <span className="font-mono text-lg font-semibold">{signal.score}</span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="rounded-md bg-muted/50 px-2 py-1.5">
                <div className="text-muted-foreground">買いスコア</div>
                <div className="font-mono text-buy">{signal.buy_score}</div>
              </div>
              <div className="rounded-md bg-muted/50 px-2 py-1.5">
                <div className="text-muted-foreground">売りスコア</div>
                <div className="font-mono text-sell">{signal.sell_score}</div>
              </div>
            </div>

            <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
              <span className="rounded-md border border-border px-2 py-1">
                {TREND_LABEL[signal.regime.trend] ?? signal.regime.trend}
              </span>
              <span className="rounded-md border border-border px-2 py-1">
                {VOLATILITY_LABEL[signal.regime.volatility] ?? signal.regime.volatility}
              </span>
            </div>

            <div className="flex flex-col gap-2">
              <div className="text-xs font-medium text-muted-foreground">判定根拠</div>
              <ul className="flex flex-col gap-1.5">
                {signal.reasons.map((reason, idx) => (
                  <li
                    key={idx}
                    className={cn(
                      "flex items-start gap-2 text-xs",
                      reason.status === "failed" && "text-muted-foreground"
                    )}
                  >
                    <ReasonIcon status={reason.status} />
                    <span className="flex-1">{reason.text}</span>
                    <span className="font-mono text-muted-foreground">{reason.points}pt</span>
                  </li>
                ))}
              </ul>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
