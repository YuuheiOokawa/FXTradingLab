"use client";

import { useQuery } from "@tanstack/react-query";

import { Card, CardContent } from "@/components/ui/card";
import { SignalBadge } from "@/components/signal-badge";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Granularity, SignalResponse } from "@/types/api";

const POLL_MS = 15000;

export function SignalCard({
  instrument,
  granularity,
  selected,
  onSelect,
}: {
  instrument: string;
  granularity: Granularity;
  selected: boolean;
  onSelect: () => void;
}) {
  const { data, isLoading, isError } = useQuery<SignalResponse>({
    queryKey: ["signal", instrument, granularity],
    queryFn: () => api.get(`/signals/${instrument}?granularity=${granularity}`),
    refetchInterval: POLL_MS,
  });

  const isBuy = data?.direction === "BUY";

  return (
    <button type="button" onClick={onSelect} className="text-left">
      <Card
        className={cn(
          "cursor-pointer transition-colors hover:border-primary/50",
          selected && "border-primary ring-1 ring-primary"
        )}
      >
        <CardContent className="flex flex-col gap-2 p-4">
          <div className="flex items-center justify-between">
            <span className="font-semibold">{instrument.replace("_", "/")}</span>
            {data && <SignalBadge label={data.label} />}
          </div>
          {isLoading && <span className="text-sm text-muted-foreground">読み込み中...</span>}
          {isError && <span className="text-sm text-sell">取得エラー</span>}
          {data && (
            <div className="flex items-center justify-between">
              <span className={cn("text-2xl font-bold tabular-nums", isBuy ? "text-buy" : "text-sell")}>
                {data.score}
                <span className="text-sm text-muted-foreground font-normal">/100</span>
              </span>
              <span className="text-xs text-muted-foreground">
                買{data.buy_score} / 売{data.sell_score}
              </span>
            </div>
          )}
        </CardContent>
      </Card>
    </button>
  );
}
