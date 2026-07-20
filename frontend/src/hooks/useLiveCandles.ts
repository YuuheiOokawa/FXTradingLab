"use client";

import { useEffect, useState } from "react";

import { priceSocket, type CandleMessage } from "@/lib/priceSocket";
import type { Candle, Granularity } from "@/types/api";

/**
 * Merges an initial REST-fetched candle series with incremental WebSocket
 * candle_update/candle_close events (docs/07_REALTIME_DATA_DESIGN.md): same-bar
 * updates mutate the last candle in place, a bar close appends a new one. The
 * chart never re-fetches history on every tick.
 */
export function useLiveCandles(instrument: string, granularity: Granularity, initial: Candle[]) {
  const [candles, setCandles] = useState<Candle[]>(initial);

  useEffect(() => {
    setCandles(initial);
  }, [instrument, granularity, initial]);

  useEffect(() => {
    if (!priceSocket) return;
    const unsubscribe = priceSocket.subscribe([instrument], (msg) => {
      if (msg.type !== "candle_update" && msg.type !== "candle_close") return;
      const m = msg as CandleMessage;
      if (m.instrument !== instrument || m.granularity !== granularity) return;
      const incoming = m.candle as Candle;
      setCandles((prev) => {
        if (prev.length === 0) return [incoming];
        const last = prev[prev.length - 1];
        if (last.open_time === incoming.open_time) {
          return [...prev.slice(0, -1), incoming];
        }
        if (new Date(incoming.open_time) > new Date(last.open_time)) {
          return [...prev, incoming];
        }
        return prev;
      });
    });
    return unsubscribe;
  }, [instrument, granularity]);

  return candles;
}
