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
    const url = wsUrl(`/ws/prices${instruments ? `?instruments=${instruments}` : ""}`);
    const ws = new WebSocket(url);
    this.ws = ws;

    ws.onopen = () => {
      this.connecting = false;
      this.reconnectDelay = 1000;
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
