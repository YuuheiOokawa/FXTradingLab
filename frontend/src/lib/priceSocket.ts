"use client";

import { wsUrl } from "@/lib/api";

export interface TickMessage {
  type: "tick";
  instrument: string;
  bid: number;
  ask: number;
  mid: number;
  spread: number;
  ts: string;
}

export interface CandleMessage {
  type: "candle_update" | "candle_close";
  instrument: string;
  granularity: string;
  candle: {
    instrument: string;
    granularity: string;
    open_time: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    is_final: boolean;
  };
}

export type PriceSocketMessage = TickMessage | CandleMessage;
type Listener = (msg: PriceSocketMessage) => void;

/**
 * Single shared WebSocket connection for /ws/prices (docs/07_REALTIME_DATA_DESIGN.md
 * — "the frontend never polls REST for live price ticks"). Components subscribe to
 * the instruments they care about; the socket tracks the union of all active
 * subscriptions and reconnects with backoff on drop.
 */
class PriceSocketManager {
  private ws: WebSocket | null = null;
  private listeners = new Set<Listener>();
  private subscribedInstruments = new Set<string>();
  private reconnectDelay = 1000;
  private connecting = false;

  private ensureConnected() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) return;
    if (this.connecting) return;
    this.connecting = true;
    const instruments = Array.from(this.subscribedInstruments).join(",");
    // Fetching a ticket is async (docs/11_SECURITY.md "BFF migration") — a
    // fresh one is required for every connection attempt since each is
    // single-use, so this can't be hoisted out of ensureConnected().
    wsUrl(`/ws/prices${instruments ? `?instruments=${instruments}` : ""}`)
      .then((url) => this._connect(url))
      .catch(() => {
        this.connecting = false;
        if (this.listeners.size > 0) {
          setTimeout(() => this.ensureConnected(), this.reconnectDelay);
          this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30000);
        }
      });
  }

  private _connect(url: string) {
    const ws = new WebSocket(url);
    this.ws = ws;

    ws.onopen = () => {
      this.connecting = false;
      this.reconnectDelay = 1000;
      // Flush every instrument subscribed so far — including ones requested
      // while the handshake was still in flight, which would otherwise never
      // get a "subscribe" message sent at all (the bug this fixes: a
      // subscribe() call arriving during CONNECTING silently dropped its
      // message since the old code only sent it when readyState was already
      // OPEN, and never retried). Re-subscribing an instrument the backend
      // already has via the initial `?instruments=` query param is harmless —
      // Redis psubscribe on an existing pattern is a no-op.
      if (this.subscribedInstruments.size > 0) {
        ws.send(JSON.stringify({ type: "subscribe", instruments: Array.from(this.subscribedInstruments) }));
      }
    };
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as PriceSocketMessage;
        this.listeners.forEach((l) => l(msg));
      } catch {
        // ignore malformed frame
      }
    };
    ws.onclose = () => {
      this.connecting = false;
      this.ws = null;
      if (this.listeners.size > 0) {
        setTimeout(() => this.ensureConnected(), this.reconnectDelay);
        this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30000);
      }
    };
    ws.onerror = () => ws.close();
  }

  /** For LIVE/STALE/DISCONNECTED indicators (docs/15_PRODUCTION_READINESS_REVIEW.md
   * "Realtime resilience") — never show a price as live if the socket itself
   * isn't actually open, regardless of how recent the last tick looked. */
  getConnectionState(): "open" | "connecting" | "closed" {
    if (!this.ws) return "closed";
    if (this.ws.readyState === WebSocket.OPEN) return "open";
    if (this.ws.readyState === WebSocket.CONNECTING) return "connecting";
    return "closed";
  }

  subscribe(instruments: string[], listener: Listener): () => void {
    this.listeners.add(listener);
    const newOnes = instruments.filter((i) => !this.subscribedInstruments.has(i));
    instruments.forEach((i) => this.subscribedInstruments.add(i));
    this.ensureConnected();
    if (newOnes.length > 0 && this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "subscribe", instruments: newOnes }));
    }
    return () => {
      this.listeners.delete(listener);
    };
  }
}

export const priceSocket = typeof window !== "undefined" ? new PriceSocketManager() : null;
