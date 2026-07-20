"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";

import { api } from "@/lib/api";
import { useLivePrice } from "@/hooks/useLivePrice";
import { Button } from "@/components/ui/button";
import { cn, formatPct, formatPrice } from "@/lib/utils";
import type { Instrument, PriceSnapshot } from "@/types/api";

export function InstrumentRow({
  instrument,
  onRemove,
  removing,
}: {
  instrument: Instrument;
  onRemove: (symbol: string) => void;
  removing: boolean;
}) {
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

  const precision = instrument.price_precision;
  const bid = live?.bid ?? snapshot?.bid;
  const ask = live?.ask ?? snapshot?.ask;
  const mid = live?.mid ?? snapshot?.mid;
  const spreadPrice = live?.spread ?? snapshot?.spread;
  const spreadPips = spreadPrice !== undefined ? spreadPrice / instrument.pip_size : undefined;
  const changePct = snapshot?.change_pct;

  return (
    <tr className="border-b border-border/60 last:border-0 hover:bg-muted/30">
      <td className="py-3 pr-4">
        <Link href={`/chart?symbol=${instrument.symbol}`} className="block">
          <div className="text-sm font-medium text-foreground">{instrument.display_name}</div>
          <div className="text-xs text-muted-foreground">{instrument.symbol}</div>
        </Link>
      </td>
      <td className="py-3 pr-4 tabular-nums text-foreground">{formatPrice(bid, precision)}</td>
      <td className="py-3 pr-4 tabular-nums text-foreground">{formatPrice(ask, precision)}</td>
      <td className="py-3 pr-4 tabular-nums font-medium text-foreground">{formatPrice(mid, precision)}</td>
      <td className="py-3 pr-4 tabular-nums text-muted-foreground">
        {spreadPips !== undefined ? `${spreadPips.toFixed(1)}pips` : "—"}
      </td>
      <td className="py-3 pr-4 tabular-nums text-muted-foreground">{formatPrice(snapshot?.day_high, precision)}</td>
      <td className="py-3 pr-4 tabular-nums text-muted-foreground">{formatPrice(snapshot?.day_low, precision)}</td>
      <td
        className={cn(
          "py-3 pr-4 tabular-nums font-medium",
          changePct !== undefined && changePct > 0 && "text-buy",
          changePct !== undefined && changePct < 0 && "text-sell",
          (changePct === undefined || changePct === 0) && "text-muted-foreground"
        )}
      >
        {formatPct(changePct)}
      </td>
      <td className="py-3 text-right">
        <Button
          variant="ghost"
          size="icon"
          disabled={removing}
          onClick={(e) => {
            e.preventDefault();
            onRemove(instrument.symbol);
          }}
          aria-label={`${instrument.symbol}の監視を解除`}
        >
          <Trash2 size={16} className="text-muted-foreground" />
        </Button>
      </td>
    </tr>
  );
}
