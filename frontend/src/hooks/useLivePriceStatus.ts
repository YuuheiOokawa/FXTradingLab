"use client";

import { useEffect, useRef, useState } from "react";

import { priceSocket, type TickMessage } from "@/lib/priceSocket";

export type PriceStatus = "live" | "stale" | "disconnected" | "connecting";

// Matches the backend's PRICE_STALE_SECONDS default (app/core/config.py) — a
// price older than this is no longer safe to treat as "current".
const STALE_AFTER_MS = 10_000;
const POLL_MS = 1_000;

/**
 * LIVE / STALE / DISCONNECTED indicator (docs/15_PRODUCTION_READINESS_REVIEW.md
 * "Realtime resilience" — "a stale price must never keep displaying as LIVE").
 * Deliberately separate from useLivePrice() so existing call sites don't need
 * to change; components that want the status subscribe to this alongside it.
 */
export function useLivePriceStatus(instrument: string): PriceStatus {
  const [status, setStatus] = useState<PriceStatus>("connecting");
  const lastTickAt = useRef<number | null>(null);

  useEffect(() => {
    if (!priceSocket) return;
    lastTickAt.current = null;
    setStatus("connecting");

    const unsubscribe = priceSocket.subscribe([instrument], (msg) => {
      if (msg.type === "tick" && (msg as TickMessage).instrument === instrument) {
        lastTickAt.current = Date.now();
      }
    });

    const interval = setInterval(() => {
      const connectionState = priceSocket?.getConnectionState() ?? "closed";
      if (connectionState !== "open") {
        setStatus("disconnected");
        return;
      }
      if (lastTickAt.current === null) {
        setStatus("connecting");
        return;
      }
      setStatus(Date.now() - lastTickAt.current > STALE_AFTER_MS ? "stale" : "live");
    }, POLL_MS);

    return () => {
      unsubscribe();
      clearInterval(interval);
    };
  }, [instrument]);

  return status;
}
