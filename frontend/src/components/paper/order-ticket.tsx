"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2 } from "lucide-react";

import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { formatPrice } from "@/lib/utils";
import type { Direction, Instrument, PriceSnapshot } from "@/types/api";

interface OrderResponse {
  approved: boolean;
  order_id: string;
  position_id: string;
}

export function OrderTicket() {
  const queryClient = useQueryClient();
  const [instrument, setInstrument] = useState("USD_JPY");
  const [direction, setDirection] = useState<Direction>("BUY");
  const [size, setSize] = useState(10000);
  const [stopLoss, setStopLoss] = useState<number | "">("");
  const [takeProfit, setTakeProfit] = useState<number | "">("");
  const [lastResult, setLastResult] = useState<{ ok: boolean; message: string } | null>(null);

  const { data: instruments } = useQuery<Instrument[]>({
    queryKey: ["instruments"],
    queryFn: () => api.get("/instruments"),
    staleTime: 60_000,
  });

  const { data: price } = useQuery<PriceSnapshot>({
    queryKey: ["price", instrument],
    queryFn: () => api.get(`/instruments/${instrument}/price`),
    refetchInterval: 3000,
  });

  const selectedInstrument = instruments?.find((i) => i.symbol === instrument);
  const pipSize = selectedInstrument?.pip_size ?? 0.01;
  const precision = selectedInstrument?.price_precision ?? 3;
  const entryEstimate = price ? (direction === "BUY" ? price.ask : price.bid) : null;

  const lossDistance =
    entryEstimate != null && stopLoss !== ""
      ? direction === "BUY"
        ? entryEstimate - Number(stopLoss)
        : Number(stopLoss) - entryEstimate
      : null;
  const profitDistance =
    entryEstimate != null && takeProfit !== ""
      ? direction === "BUY"
        ? Number(takeProfit) - entryEstimate
        : entryEstimate - Number(takeProfit)
      : null;
  const maxLoss = lossDistance != null ? lossDistance * size : null;
  const maxProfit = profitDistance != null ? profitDistance * size : null;
  const rr = lossDistance && profitDistance && lossDistance > 0 ? profitDistance / lossDistance : null;

  const mutation = useMutation<OrderResponse, ApiError, void>({
    mutationFn: () =>
      api.post<OrderResponse>("/paper/orders", {
        instrument,
        direction,
        size,
        stop_loss: stopLoss === "" ? null : Number(stopLoss),
        take_profit: takeProfit === "" ? null : Number(takeProfit),
        idempotency_key: crypto.randomUUID(),
      }),
    onSuccess: (data) => {
      setLastResult({ ok: true, message: `注文が約定しました (position: ${data.position_id.slice(0, 8)}...)` });
      queryClient.invalidateQueries({ queryKey: ["paper-positions"] });
      queryClient.invalidateQueries({ queryKey: ["paper-account"] });
      setStopLoss("");
      setTakeProfit("");
    },
    onError: (err) => {
      setLastResult({ ok: false, message: `${err.code ?? "REJECTED"}: ${err.message}` });
    },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>注文チケット (Paper Trading)</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-muted-foreground">通貨ペア</span>
            <Select value={instrument} onChange={(e) => setInstrument(e.target.value)}>
              {(instruments ?? []).map((inst) => (
                <option key={inst.symbol} value={inst.symbol}>
                  {inst.display_name} ({inst.symbol})
                </option>
              ))}
              {!instruments?.length && <option value="USD_JPY">USD_JPY</option>}
            </Select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-muted-foreground">数量 (units)</span>
            <Input type="number" min={1} step={1000} value={size} onChange={(e) => setSize(Number(e.target.value))} />
          </label>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <Button type="button" variant={direction === "BUY" ? "buy" : "outline"} onClick={() => setDirection("BUY")}>
            BUY {price && `@ ${formatPrice(price.ask, precision)}`}
          </Button>
          <Button type="button" variant={direction === "SELL" ? "sell" : "outline"} onClick={() => setDirection("SELL")}>
            SELL {price && `@ ${formatPrice(price.bid, precision)}`}
          </Button>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-muted-foreground">Stop Loss (価格)</span>
            <Input
              type="number"
              step={pipSize}
              value={stopLoss}
              onChange={(e) => setStopLoss(e.target.value === "" ? "" : Number(e.target.value))}
              placeholder={entryEstimate ? formatPrice(entryEstimate, precision) : "—"}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-muted-foreground">Take Profit (価格)</span>
            <Input
              type="number"
              step={pipSize}
              value={takeProfit}
              onChange={(e) => setTakeProfit(e.target.value === "" ? "" : Number(e.target.value))}
              placeholder={entryEstimate ? formatPrice(entryEstimate, precision) : "—"}
            />
          </label>
        </div>

        <div className="grid grid-cols-3 gap-2 rounded-lg border border-border bg-muted/20 p-3 text-xs">
          <div>
            <div className="text-muted-foreground">最大損失(概算)</div>
            <div className={maxLoss != null ? "font-semibold text-sell" : "text-muted-foreground"}>
              {maxLoss != null ? `-${Math.abs(maxLoss).toLocaleString("ja-JP", { maximumFractionDigits: 0 })}` : "—"}
            </div>
          </div>
          <div>
            <div className="text-muted-foreground">最大利益(概算)</div>
            <div className={maxProfit != null ? "font-semibold text-buy" : "text-muted-foreground"}>
              {maxProfit != null ? `+${Math.abs(maxProfit).toLocaleString("ja-JP", { maximumFractionDigits: 0 })}` : "—"}
            </div>
          </div>
          <div>
            <div className="text-muted-foreground">リスクリワード比</div>
            <div className="font-semibold">{rr != null ? `1 : ${rr.toFixed(2)}` : "—"}</div>
          </div>
        </div>

        <Button
          className="w-full"
          variant={direction === "BUY" ? "buy" : "sell"}
          disabled={mutation.isPending || !stopLoss || !takeProfit}
          onClick={() => {
            setLastResult(null);
            mutation.mutate();
          }}
        >
          {mutation.isPending ? "発注中..." : `${direction === "BUY" ? "買い" : "売り"}注文を発注`}
        </Button>

        {lastResult && (
          <div
            className={`flex items-start gap-2 rounded-md p-3 text-xs ${
              lastResult.ok ? "bg-buy/10 text-buy" : "bg-sell/10 text-sell"
            }`}
          >
            {lastResult.ok ? <CheckCircle2 size={14} className="mt-0.5 shrink-0" /> : <AlertTriangle size={14} className="mt-0.5 shrink-0" />}
            <span>{lastResult.message}</span>
          </div>
        )}
        {!lastResult && (
          <p className="text-[11px] text-muted-foreground">
            注文はリスクエンジンによる審査を経ます。上限を超える場合は拒否理由が表示されます。
          </p>
        )}
      </CardContent>
    </Card>
  );
}
