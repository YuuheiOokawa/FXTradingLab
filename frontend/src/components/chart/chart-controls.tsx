"use client";

import { useLivePrice } from "@/hooks/useLivePrice";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { Granularity } from "@/types/api";

export const INSTRUMENTS = ["USD_JPY", "EUR_JPY", "GBP_JPY", "EUR_USD", "GBP_USD", "AUD_JPY"] as const;
export const GRANULARITIES: Granularity[] = ["M1", "M5", "M15", "H1", "H4", "D"];

function pricePrecision(symbol: string): number {
  return symbol.includes("JPY") ? 3 : 5;
}

export function ChartControls({
  symbol,
  granularity,
  onSymbolChange,
  onGranularityChange,
  showBollinger,
  onToggleBollinger,
}: {
  symbol: string;
  granularity: Granularity;
  onSymbolChange: (symbol: string) => void;
  onGranularityChange: (granularity: Granularity) => void;
  showBollinger: boolean;
  onToggleBollinger: (show: boolean) => void;
}) {
  const tick = useLivePrice(symbol);
  const precision = pricePrecision(symbol);

  return (
    <div className="flex flex-wrap items-center gap-4 rounded-lg border border-border bg-card p-3">
      <div className="flex items-center gap-2">
        <label className="text-xs text-muted-foreground">通貨ペア</label>
        <Select
          value={symbol}
          onChange={(e) => onSymbolChange(e.target.value)}
          className="w-32"
        >
          {INSTRUMENTS.map((inst) => (
            <option key={inst} value={inst}>
              {inst.replace("_", "/")}
            </option>
          ))}
        </Select>
      </div>

      <div className="flex items-center gap-1">
        {GRANULARITIES.map((g) => (
          <Button
            key={g}
            type="button"
            size="sm"
            variant={g === granularity ? "default" : "outline"}
            onClick={() => onGranularityChange(g)}
          >
            {g}
          </Button>
        ))}
      </div>

      <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <input
          type="checkbox"
          checked={showBollinger}
          onChange={(e) => onToggleBollinger(e.target.checked)}
          className="h-3.5 w-3.5 rounded border-border"
        />
        ボリンジャーバンド
      </label>

      <div className="ml-auto flex items-center gap-4 font-mono text-sm">
        {tick ? (
          <>
            <span className="text-muted-foreground">
              Bid <span className="text-sell">{tick.bid.toFixed(precision)}</span>
            </span>
            <span className="text-muted-foreground">
              Ask <span className="text-buy">{tick.ask.toFixed(precision)}</span>
            </span>
            <span className={cn("text-xs text-muted-foreground")}>
              Spread {(tick.spread * (precision === 3 ? 100 : 10000)).toFixed(1)}pips
            </span>
          </>
        ) : (
          <span className="text-xs text-muted-foreground">価格取得中...</span>
        )}
      </div>
    </div>
  );
}
