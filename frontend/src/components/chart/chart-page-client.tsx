"use client";

import { useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { useLiveCandles } from "@/hooks/useLiveCandles";
import type { Candle, Granularity, SignalResponse } from "@/types/api";

import { CandleChart } from "./candle-chart";
import { ChartControls, GRANULARITIES, INSTRUMENTS } from "./chart-controls";
import { MacdPane } from "./macd-pane";
import { RsiPane } from "./rsi-pane";
import { SignalPanel } from "./signal-panel";

const DEFAULT_SYMBOL = "USD_JPY";
const DEFAULT_GRANULARITY: Granularity = "M15";

function parseSymbol(v: string | null): string {
  if (v && (INSTRUMENTS as readonly string[]).includes(v)) return v;
  return DEFAULT_SYMBOL;
}

function parseGranularity(v: string | null): Granularity {
  if (v && (GRANULARITIES as string[]).includes(v)) return v as Granularity;
  return DEFAULT_GRANULARITY;
}

export function ChartPageClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const symbol = parseSymbol(searchParams.get("symbol"));
  const granularity = parseGranularity(searchParams.get("granularity"));
  const [showBollinger, setShowBollinger] = useState(false);

  function updateParams(next: { symbol?: string; granularity?: Granularity }) {
    const params = new URLSearchParams(searchParams.toString());
    if (next.symbol) params.set("symbol", next.symbol);
    if (next.granularity) params.set("granularity", next.granularity);
    router.replace(`/chart?${params.toString()}`);
  }

  const candlesQuery = useQuery<Candle[]>({
    queryKey: ["chart-candles", symbol, granularity],
    queryFn: () => api.get(`/instruments/${symbol}/candles?granularity=${granularity}&count=300`),
  });

  const signalQuery = useQuery<SignalResponse>({
    queryKey: ["chart-signal", symbol, granularity],
    queryFn: () => api.get(`/signals/${symbol}?granularity=${granularity}`),
    refetchInterval: 20000,
  });

  const initialCandles = useMemo(() => candlesQuery.data ?? [], [candlesQuery.data]);
  const candles = useLiveCandles(symbol, granularity, initialCandles);

  return (
    <div className="flex flex-col gap-4 p-4">
      <ChartControls
        symbol={symbol}
        granularity={granularity}
        onSymbolChange={(s) => updateParams({ symbol: s })}
        onGranularityChange={(g) => updateParams({ granularity: g })}
        showBollinger={showBollinger}
        onToggleBollinger={setShowBollinger}
      />

      {candlesQuery.isError && (
        <p className="text-sm text-destructive">ローソク足データの取得に失敗しました。</p>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="flex flex-col gap-2">
          <CandleChart candles={candles} showBollinger={showBollinger} signal={signalQuery.data} />
          <RsiPane candles={candles} />
          <MacdPane candles={candles} />
        </div>
        <SignalPanel signal={signalQuery.data} isLoading={signalQuery.isLoading} error={signalQuery.error} />
      </div>
    </div>
  );
}
