"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { Granularity, Instrument } from "@/types/api";

export interface BacktestFormValues {
  pair: string;
  timeframe: Granularity;
  candle_count: number;
  initial_capital: number;
  risk_pct: number;
  spread_pips: number;
  slippage_pips: number;
  commission_per_lot: number;
  stop_loss_pips: number;
  take_profit_pips: number;
  trailing_stop_pips: number | null;
  in_sample_ratio: number;
}

const DEFAULT_VALUES: BacktestFormValues = {
  pair: "USD_JPY",
  timeframe: "M15",
  candle_count: 1500,
  initial_capital: 1_000_000,
  risk_pct: 1.0,
  spread_pips: 1.5,
  slippage_pips: 0.3,
  commission_per_lot: 0.0,
  stop_loss_pips: 30.0,
  take_profit_pips: 60.0,
  trailing_stop_pips: null,
  in_sample_ratio: 0.7,
};

const TIMEFRAMES: Granularity[] = ["M1", "M5", "M15", "H1", "H4", "D"];

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {children}
      {hint && <span className="text-[11px] text-muted-foreground">{hint}</span>}
    </label>
  );
}

export function BacktestForm({
  onSubmit,
  pending,
}: {
  onSubmit: (values: BacktestFormValues) => void;
  pending: boolean;
}) {
  const [values, setValues] = useState<BacktestFormValues>(DEFAULT_VALUES);
  const [trailingEnabled, setTrailingEnabled] = useState(false);

  const { data: instruments } = useQuery<Instrument[]>({
    queryKey: ["instruments"],
    queryFn: () => api.get("/instruments"),
    staleTime: 60_000,
  });

  function set<K extends keyof BacktestFormValues>(key: K, value: BacktestFormValues[K]) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSubmit({
      ...values,
      trailing_stop_pips: trailingEnabled ? values.trailing_stop_pips : null,
    });
  }

  return (
    <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
      <Field label="通貨ペア">
        <Select value={values.pair} onChange={(e) => set("pair", e.target.value)}>
          {(instruments ?? []).map((inst) => (
            <option key={inst.symbol} value={inst.symbol}>
              {inst.display_name} ({inst.symbol})
            </option>
          ))}
          {!instruments?.length && <option value="USD_JPY">USD_JPY</option>}
        </Select>
      </Field>

      <Field label="時間足">
        <Select value={values.timeframe} onChange={(e) => set("timeframe", e.target.value as Granularity)}>
          {TIMEFRAMES.map((tf) => (
            <option key={tf} value={tf}>
              {tf}
            </option>
          ))}
        </Select>
      </Field>

      <Field label="ローソク足本数" hint="300〜5000">
        <Input
          type="number"
          min={300}
          max={5000}
          step={100}
          value={values.candle_count}
          onChange={(e) => set("candle_count", Number(e.target.value))}
        />
      </Field>

      <Field label="初期資金">
        <Input
          type="number"
          min={0}
          step={10000}
          value={values.initial_capital}
          onChange={(e) => set("initial_capital", Number(e.target.value))}
        />
      </Field>

      <Field label="リスク% / 取引" hint="1トレードあたりの資金比率">
        <Input
          type="number"
          min={0.1}
          max={10}
          step={0.1}
          value={values.risk_pct}
          onChange={(e) => set("risk_pct", Number(e.target.value))}
        />
      </Field>

      <Field label="スプレッド (pips)">
        <Input
          type="number"
          min={0}
          step={0.1}
          value={values.spread_pips}
          onChange={(e) => set("spread_pips", Number(e.target.value))}
        />
      </Field>

      <Field label="スリッページ (pips)">
        <Input
          type="number"
          min={0}
          step={0.1}
          value={values.slippage_pips}
          onChange={(e) => set("slippage_pips", Number(e.target.value))}
        />
      </Field>

      <Field label="手数料 / ロット">
        <Input
          type="number"
          min={0}
          step={0.1}
          value={values.commission_per_lot}
          onChange={(e) => set("commission_per_lot", Number(e.target.value))}
        />
      </Field>

      <Field label="Stop Loss (pips)">
        <Input
          type="number"
          min={1}
          step={1}
          value={values.stop_loss_pips}
          onChange={(e) => set("stop_loss_pips", Number(e.target.value))}
        />
      </Field>

      <Field label="Take Profit (pips)">
        <Input
          type="number"
          min={1}
          step={1}
          value={values.take_profit_pips}
          onChange={(e) => set("take_profit_pips", Number(e.target.value))}
        />
      </Field>

      <Field label="Trailing Stop (pips)" hint="任意">
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={trailingEnabled}
            onChange={(e) => {
              setTrailingEnabled(e.target.checked);
              if (e.target.checked && values.trailing_stop_pips === null) set("trailing_stop_pips", 20);
            }}
            className="h-4 w-4 rounded border-border"
          />
          <Input
            type="number"
            min={1}
            step={1}
            disabled={!trailingEnabled}
            value={values.trailing_stop_pips ?? ""}
            onChange={(e) => set("trailing_stop_pips", Number(e.target.value))}
          />
        </div>
      </Field>

      <Field label="In-Sample比率" hint="0.3〜0.9 (学習期間の割合)">
        <Input
          type="number"
          min={0.3}
          max={0.9}
          step={0.05}
          value={values.in_sample_ratio}
          onChange={(e) => set("in_sample_ratio", Number(e.target.value))}
        />
      </Field>

      <div className="col-span-2 flex items-end sm:col-span-3 lg:col-span-4">
        <Button type="submit" disabled={pending} className="w-full sm:w-auto">
          {pending ? "実行中..." : "バックテスト実行"}
        </Button>
      </div>
    </form>
  );
}
