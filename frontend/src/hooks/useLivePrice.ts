"use client";

import { useEffect, useState } from "react";

import { priceSocket, type TickMessage } from "@/lib/priceSocket";

export interface LiveTick {
  bid: number;
  ask: number;
  mid: number;
  spread: number;
  ts: string;
}

/** Subscribes to live bid/ask/mid ticks for one instrument over the shared
 * WebSocket connection (docs/07_REALTIME_DATA_DESIGN.md). */
export function useLivePrice(instrument: string, initial?: LiveTick | null) {
  const [tick, setTick] = useState<LiveTick | null>(initial ?? null);

  useEffect(() => {
    if (!priceSocket) return;
    const unsubscribe = priceSocket.subscribe([instrument], (msg) => {
      if (msg.type === "tick" && msg.instrument === instrument) {
        const t = msg as TickMessage;
        setTick({ bid: t.bid, ask: t.ask, mid: t.mid, spread: t.spread, ts: t.ts });
      }
    });
    return unsubscribe;
  }, [instrument]);

  return tick;
}
