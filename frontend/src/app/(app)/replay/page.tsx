"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Card, CardContent } from "@/components/ui/card";
import { CandleChart } from "@/components/replay/candle-chart";
import { DecisionLog } from "@/components/replay/decision-log";
import { ReplayControls } from "@/components/replay/replay-controls";
import { SetupForm, type ReplaySetup } from "@/components/replay/setup-form";
import { api } from "@/lib/api";
import type { ReplaySessionState } from "@/types/api";

export default function ReplayPage() {
  const queryClient = useQueryClient();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [autoplay, setAutoplay] = useState(false);
  const [speed, setSpeed] = useState(1);

  const sessionQuery = useQuery<ReplaySessionState>({
    queryKey: ["replay-session", sessionId],
    queryFn: () => api.get(`/replay/sessions/${sessionId}`),
    enabled: !!sessionId,
  });

  const session = sessionQuery.data;

  const createMutation = useMutation({
    mutationFn: (setup: ReplaySetup) => api.post<ReplaySessionState>("/replay/sessions", setup),
    onSuccess: (data) => {
      queryClient.setQueryData(["replay-session", data.id], data);
      setSessionId(data.id);
      setAutoplay(false);
    },
  });

  const stepMutation = useMutation({
    mutationFn: () => api.post<ReplaySessionState>(`/replay/sessions/${sessionId}/step`),
    onSuccess: (data) => queryClient.setQueryData(["replay-session", sessionId], data),
  });

  const decideMutation = useMutation({
    mutationFn: ({ action, stopLossPips, takeProfitPips }: { action: "BUY" | "SELL" | "SKIP"; stopLossPips?: number; takeProfitPips?: number }) =>
      api.post<ReplaySessionState>(`/replay/sessions/${sessionId}/decide`, {
        action,
        stop_loss_pips: stopLossPips ?? null,
        take_profit_pips: takeProfitPips ?? null,
      }),
    onSuccess: (data) => queryClient.setQueryData(["replay-session", sessionId], data),
  });

  const closeMutation = useMutation({
    mutationFn: () => api.post<ReplaySessionState>(`/replay/sessions/${sessionId}/close`),
    onSuccess: (data) => queryClient.setQueryData(["replay-session", sessionId], data),
  });

  const stepPendingRef = useRef(false);
  stepPendingRef.current = stepMutation.isPending;

  // Autoplay: step at an interval scaled by speed (base 1000ms / speed).
  useEffect(() => {
    if (!autoplay || !session || session.is_at_end) return;
    const interval = setInterval(() => {
      if (stepPendingRef.current) return;
      stepMutation.mutate();
    }, 1000 / speed);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoplay, speed, session?.is_at_end, sessionId]);

  useEffect(() => {
    if (session?.is_at_end) setAutoplay(false);
  }, [session?.is_at_end]);

  if (!sessionId || !session) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold">リプレイ</h1>
          <p className="text-sm text-muted-foreground">過去の相場を一本ずつ再生し、未来を見ずに売買判断を練習します。</p>
        </div>
        <div className="max-w-md">
          <SetupForm onStart={(setup) => createMutation.mutate(setup)} starting={createMutation.isPending} />
        </div>
        {createMutation.isError && (
          <p className="text-sm text-sell">セッション作成に失敗しました: {(createMutation.error as Error).message}</p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">リプレイ</h1>
          <p className="text-sm text-muted-foreground">
            {session.instrument.replace("_", "/")} · {session.granularity} · {session.current_index + 1}/{session.total_candles}本目
            {session.training_mode && <span className="ml-2 text-buy">トレーニングモード</span>}
          </p>
        </div>
        <button
          type="button"
          className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
          onClick={() => {
            setSessionId(null);
            setAutoplay(false);
          }}
        >
          新しいセッションを開始
        </button>
      </div>

      <Card>
        <CardContent className="space-y-4 p-4">
          <CandleChart candles={session.candles} />
          <ReplayControls
            isAtEnd={session.is_at_end}
            autoplay={autoplay}
            onToggleAutoplay={() => setAutoplay((v) => !v)}
            speed={speed}
            onChangeSpeed={setSpeed}
            onStep={() => stepMutation.mutate()}
            stepping={stepMutation.isPending}
            hasOpenDecision={session.has_open_decision}
            onDecide={(action, stopLossPips, takeProfitPips) => decideMutation.mutate({ action, stopLossPips, takeProfitPips })}
            onClose={() => closeMutation.mutate()}
            deciding={decideMutation.isPending}
            closing={closeMutation.isPending}
          />
        </CardContent>
      </Card>

      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">判断履歴</h2>
        <DecisionLog decisions={session.decisions} showExplanation />
      </div>
    </div>
  );
}
