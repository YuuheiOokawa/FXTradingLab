"use client";

import { useQueries } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { SignalBadge } from "@/components/signal-badge";
import type { Instrument, SignalResponse } from "@/types/api";

export function RecentSignals({ instruments }: { instruments: Instrument[] }) {
  const results = useQueries({
    queries: instruments.map((inst) => ({
      queryKey: ["signal", inst.symbol, "M15"],
      queryFn: () => api.get<SignalResponse>(`/signals/${inst.symbol}?granularity=M15`),
      refetchInterval: 30000,
    })),
  });

  const rows = instruments
    .map((inst, i) => ({ inst, signal: results[i]?.data }))
    .filter((r): r is { inst: Instrument; signal: SignalResponse } => !!r.signal);

  if (rows.length === 0) {
    return <p className="text-sm text-muted-foreground">シグナルを読み込み中...</p>;
  }

  return (
    <ul className="divide-y divide-border">
      {rows.map(({ inst, signal }) => {
        const topReason = [...signal.reasons].sort((a, b) => b.points - a.points)[0];
        return (
          <li key={inst.symbol} className="flex items-center justify-between gap-4 py-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-foreground">{inst.display_name}</span>
                <span className="text-xs text-muted-foreground">{inst.symbol}</span>
              </div>
              {topReason && <p className="mt-0.5 truncate text-xs text-muted-foreground">{topReason.text}</p>}
            </div>
            <div className="flex shrink-0 items-center gap-3">
              <span className="text-xs tabular-nums text-muted-foreground">
                買{signal.buy_score} / 売{signal.sell_score}
              </span>
              <SignalBadge label={signal.label} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
