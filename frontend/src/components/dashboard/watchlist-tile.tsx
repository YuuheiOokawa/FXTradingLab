"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { useLivePrice } from "@/hooks/useLivePrice";
import { SignalBadge } from "@/components/signal-badge";
import { cn, formatPct, formatPrice } from "@/lib/utils";
import type { Instrument, PriceSnapshot, SignalResponse } from "@/types/api";

export function WatchlistTile({ instrument }: { instrument: Instrument }) {
  const { data: snapshot } = useQuery<PriceSnapshot>({
    queryKey: ["price-snapshot", instrument.symbol],
    queryFn: () => api.get(`/instruments/${instrument.symbol}/price`),
    refetchInterval: 15000,
  });

  const live = useLivePrice(
    instrument.symbol,
    snapshot
      ? { bid: snapshot.bid, ask: snapshot.ask, mid: snapshot.mid, spread: snapshot.spread, ts: snapshot.ts }
      : null
  );

  const { data: signal } = useQuery<SignalResponse>({
    queryKey: ["signal", instrument.symbol, "M15"],
    queryFn: () => api.get(`/signals/${instrument.symbol}?granularity=M15`),
    refetchInterval: 30000,
  });

  const precision = instrument.price_precision;
  const mid = live?.mid ?? snapshot?.mid;
  const bid = live?.bid ?? snapshot?.bid;
  const ask = live?.ask ?? snapshot?.ask;
  const spreadPrice = live?.spread ?? snapshot?.spread;
  const spreadPips = spreadPrice !== undefined ? spreadPrice / instrument.pip_size : undefined;
  const changePct = snapshot?.change_pct;

  return (
    <Link
      href={`/chart?symbol=${instrument.symbol}`}
      className="block rounded-lg border border-border bg-card p-4 transition-colors hover:border-primary/50"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-foreground">{instrument.display_name}</div>
          <div className="text-xs text-muted-foreground">{instrument.symbol}</div>
        </div>
        {signal && <SignalBadge label={signal.label} />}
      </div>
      <div className="mt-3 flex items-end justify-between gap-2">
        <div className="text-2xl font-semibold tabular-nums text-foreground">{formatPrice(mid, precision)}</div>
        <div
          className={cn(
            "text-sm font-medium tabular-nums",
            changePct !== undefined && changePct > 0 && "text-buy",
            changePct !== undefined && changePct < 0 && "text-sell",
            (changePct === undefined || changePct === 0) && "text-muted-foreground"
          )}
        >
          {formatPct(changePct)}
        </div>
      </div>
      <div className="mt-2 flex justify-between text-xs text-muted-foreground tabular-nums">
        <span>Bid {formatPrice(bid, precision)}</span>
        <span>Ask {formatPrice(ask, precision)}</span>
        <span>{spreadPips !== undefined ? `${spreadPips.toFixed(1)}pips` : "—"}</span>
      </div>
    </Link>
  );
}
