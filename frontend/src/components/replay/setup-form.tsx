"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { Granularity } from "@/types/api";

const WATCHLIST = ["USD_JPY", "EUR_JPY", "GBP_JPY", "EUR_USD"];
const GRANULARITIES: Granularity[] = ["M1", "M5", "M15", "H1", "H4", "D"];

export interface ReplaySetup {
  instrument: string;
  granularity: Granularity;
  candle_count: number;
  training_mode: boolean;
}

export function SetupForm({ onStart, starting }: { onStart: (setup: ReplaySetup) => void; starting: boolean }) {
  const [instrument, setInstrument] = useState(WATCHLIST[0]);
  const [granularity, setGranularity] = useState<Granularity>("M15");
  const [candleCount, setCandleCount] = useState("500");
  const [trainingMode, setTrainingMode] = useState(true);

  const count = Number(candleCount);
  const canStart = count > 1 && !starting;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base text-foreground font-semibold">リプレイ設定</CardTitle>
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
            <label className="text-xs text-muted-foreground">時間足</label>
            <Select value={granularity} onChange={(e) => setGranularity(e.target.value as Granularity)}>
              {GRANULARITIES.map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </Select>
          </div>
        </div>

        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">ローソク足本数</label>
          <Input inputMode="numeric" value={candleCount} onChange={(e) => setCandleCount(e.target.value)} />
        </div>

        <div className="flex items-center justify-between rounded-md border border-border p-3">
          <div>
            <div className="text-sm font-medium">トレーニングモード</div>
            <div className="text-xs text-muted-foreground">判断前でも根拠(ルール評価)を常時表示します</div>
          </div>
          <Button type="button" variant={trainingMode ? "buy" : "outline"} size="sm" onClick={() => setTrainingMode((v) => !v)}>
            {trainingMode ? "ON" : "OFF"}
          </Button>
        </div>

        <Button
          className="w-full"
          disabled={!canStart}
          onClick={() => onStart({ instrument, granularity, candle_count: count, training_mode: trainingMode })}
        >
          {starting ? "開始中..." : "リプレイ開始"}
        </Button>
      </CardContent>
    </Card>
  );
}
