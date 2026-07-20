"use client";

import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useLivePrice } from "@/hooks/useLivePrice";
import { cn } from "@/lib/utils";
import type { Direction } from "@/types/api";

const WATCHLIST = ["USD_JPY", "EUR_JPY", "GBP_JPY", "EUR_USD"];
const MARGIN_RATE = 0.04;

export interface SimulationOrder {
  instrument: string;
  direction: Direction;
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  size: number;
}

export function OrderTicket({ onSubmit, submitting }: { onSubmit: (order: SimulationOrder) => void; submitting: boolean }) {
  const [instrument, setInstrument] = useState(WATCHLIST[0]);
  const [direction, setDirection] = useState<Direction>("BUY");
  const [entryPrice, setEntryPrice] = useState<string>("");
  const [stopLoss, setStopLoss] = useState<string>("");
  const [takeProfit, setTakeProfit] = useState<string>("");
  const [size, setSize] = useState<string>("10000");

  const liveTick = useLivePrice(instrument);
  const livePrice = liveTick?.mid;

  const entryNum = entryPrice !== "" ? Number(entryPrice) : livePrice ?? 0;
  const slNum = Number(stopLoss);
  const tpNum = Number(takeProfit);
  const sizeNum = Number(size);

  const maxLoss = useMemo(() => {
    if (!entryNum || !slNum || !sizeNum) return null;
    return Math.abs(entryNum - slNum) * sizeNum;
  }, [entryNum, slNum, sizeNum]);

  const maxProfit = useMemo(() => {
    if (!entryNum || !tpNum || !sizeNum) return null;
    return Math.abs(entryNum - tpNum) * sizeNum;
  }, [entryNum, tpNum, sizeNum]);

  const riskReward = useMemo(() => {
    if (!maxLoss || !maxProfit || maxLoss === 0) return null;
    return maxProfit / maxLoss;
  }, [maxLoss, maxProfit]);

  const marginEstimate = useMemo(() => {
    if (!entryNum || !sizeNum) return null;
    return entryNum * sizeNum * MARGIN_RATE;
  }, [entryNum, sizeNum]);

  const canSubmit = entryNum > 0 && slNum > 0 && tpNum > 0 && sizeNum > 0 && !submitting;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base text-foreground font-semibold">シミュレーション発注</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">通貨ペア</label>
            <Select value={instrument} onChange={(e) => setInstrument(e.target.value)}>
              {WATCHLIST.map((i) => (
                <option key={i} value={i}>
                  {i.replace("_", "/")}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">現在価格 (Mid)</label>
            <div className="flex h-9 items-center rounded-md border border-input bg-muted/40 px-3 text-sm tabular-nums">
              {livePrice ? livePrice.toFixed(3) : "取得中..."}
            </div>
          </div>
        </div>

        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">方向</label>
          <div className="grid grid-cols-2 gap-2">
            <Button
              type="button"
              variant={direction === "BUY" ? "buy" : "outline"}
              onClick={() => setDirection("BUY")}
            >
              BUY 買い
            </Button>
            <Button
              type="button"
              variant={direction === "SELL" ? "sell" : "outline"}
              onClick={() => setDirection("SELL")}
            >
              SELL 売り
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">エントリー価格</label>
            <Input
              inputMode="decimal"
              placeholder={livePrice ? livePrice.toFixed(3) : "—"}
              value={entryPrice}
              onChange={(e) => setEntryPrice(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">損切り (SL)</label>
            <Input inputMode="decimal" value={stopLoss} onChange={(e) => setStopLoss(e.target.value)} />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">利確 (TP)</label>
            <Input inputMode="decimal" value={takeProfit} onChange={(e) => setTakeProfit(e.target.value)} />
          </div>
        </div>

        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">数量 (通貨単位)</label>
          <Input inputMode="decimal" value={size} onChange={(e) => setSize(e.target.value)} />
        </div>

        <div className="grid grid-cols-2 gap-3 rounded-md border border-border bg-muted/20 p-3 text-sm sm:grid-cols-4">
          <Metric label="想定最大損失" value={maxLoss} className="text-sell" />
          <Metric label="想定利益" value={maxProfit} className="text-buy" />
          <Metric label="Risk/Reward" value={riskReward} suffix="" decimals={2} isRatio />
          <Metric label="必要証拠金概算" value={marginEstimate} note="4%概算" />
        </div>

        <Button
          className="w-full"
          variant={direction === "BUY" ? "buy" : "sell"}
          disabled={!canSubmit}
          onClick={() =>
            onSubmit({
              instrument,
              direction,
              entry_price: entryNum,
              stop_loss: slNum,
              take_profit: tpNum,
              size: sizeNum,
            })
          }
        >
          {submitting ? "発注中..." : "シミュレーション開始"}
        </Button>
      </CardContent>
    </Card>
  );
}

function Metric({
  label,
  value,
  className,
  note,
  decimals = 0,
  isRatio,
}: {
  label: string;
  value: number | null;
  className?: string;
  note?: string;
  suffix?: string;
  decimals?: number;
  isRatio?: boolean;
}) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn("font-semibold tabular-nums", className)}>
        {value === null
          ? "—"
          : isRatio
            ? `1 : ${value.toFixed(decimals)}`
            : value.toLocaleString("ja-JP", { maximumFractionDigits: decimals })}
      </div>
      {note && <div className="text-[10px] text-muted-foreground">{note}</div>}
    </div>
  );
}
