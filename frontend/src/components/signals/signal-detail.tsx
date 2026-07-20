"use client";

import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SignalBadge } from "@/components/signal-badge";
import { ReasonList } from "@/components/signals/reason-list";
import { RegimeBadges } from "@/components/signals/regime-badges";
import { ScoreDisplay } from "@/components/signals/score-display";
import { api } from "@/lib/api";
import type { Granularity, SignalResponse } from "@/types/api";

const POLL_MS = 15000;

export function SignalDetail({ instrument, granularity }: { instrument: string; granularity: Granularity }) {
  const { data, isLoading, isError, isFetching, dataUpdatedAt } = useQuery<SignalResponse>({
    queryKey: ["signal", instrument, granularity],
    queryFn: () => api.get(`/signals/${instrument}?granularity=${granularity}`),
    refetchInterval: POLL_MS,
  });

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <CardTitle className="text-base text-foreground font-semibold">
            {instrument.replace("_", "/")} <span className="text-muted-foreground font-normal">{granularity}</span>
          </CardTitle>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <RefreshCw size={12} className={isFetching ? "animate-spin" : ""} />
          {dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString("ja-JP") : "—"}
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {isLoading && <p className="text-sm text-muted-foreground">読み込み中...</p>}
        {isError && <p className="text-sm text-sell">シグナルの取得に失敗しました。</p>}
        {data && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <ScoreDisplay direction={data.direction} score={data.score} />
              <SignalBadge label={data.label} />
            </div>
            <RegimeBadges trend={data.regime.trend} volatility={data.regime.volatility} />
            <div>
              <h3 className="mb-2 text-sm font-medium text-muted-foreground">なぜ今は{data.direction === "BUY" ? "買い" : "売り"}なのか</h3>
              <ReasonList reasons={data.reasons} />
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
