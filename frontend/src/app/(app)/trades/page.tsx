"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowDownAZ, ArrowUpAZ } from "lucide-react";

import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { TradesTable } from "@/components/trades/trades-table";
import type { Direction, Instrument, TradeJournalEntry } from "@/types/api";

type SortKey = "entry_time" | "exit_time" | "pnl" | "pair";

export default function TradesPage() {
  const [source, setSource] = useState<string>("");
  const [pair, setPair] = useState<string>("");
  const [direction, setDirection] = useState<string>("");
  const [sortKey, setSortKey] = useState<SortKey>("exit_time");
  const [sortDesc, setSortDesc] = useState(true);

  const { data: instruments } = useQuery<Instrument[]>({
    queryKey: ["instruments"],
    queryFn: () => api.get("/instruments"),
    staleTime: 60_000,
  });

  const params = new URLSearchParams();
  if (source) params.set("source", source);
  if (pair) params.set("pair", pair);
  if (direction) params.set("direction", direction);
  params.set("limit", "200");

  const { data: trades, isLoading } = useQuery<TradeJournalEntry[]>({
    queryKey: ["journal-trades", source, pair, direction],
    queryFn: () => api.get(`/journal/trades?${params.toString()}`),
  });

  const sorted = useMemo(() => {
    const list = [...(trades ?? [])];
    list.sort((a, b) => {
      let cmp = 0;
      if (sortKey === "pnl") cmp = a.pnl - b.pnl;
      else if (sortKey === "pair") cmp = a.pair.localeCompare(b.pair);
      else cmp = new Date(a[sortKey]).getTime() - new Date(b[sortKey]).getTime();
      return sortDesc ? -cmp : cmp;
    });
    return list;
  }, [trades, sortKey, sortDesc]);

  const totalPnl = sorted.reduce((s, t) => s + t.pnl, 0);
  const wins = sorted.filter((t) => t.pnl > 0).length;

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold">トレード履歴</h1>
        <p className="mt-1 text-sm text-muted-foreground">バックテスト・Paper・デモ・LIVEすべての取引を横断して確認できます。</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>フィルター / 並び替え</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-muted-foreground">ソース</span>
              <Select value={source} onChange={(e) => setSource(e.target.value)} className="w-40">
                <option value="">すべて</option>
                <option value="backtest">バックテスト</option>
                <option value="paper">Paper</option>
                <option value="demo">デモ</option>
                <option value="live">LIVE</option>
              </Select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-muted-foreground">通貨ペア</span>
              <Select value={pair} onChange={(e) => setPair(e.target.value)} className="w-44">
                <option value="">すべて</option>
                {(instruments ?? []).map((i) => (
                  <option key={i.symbol} value={i.symbol}>
                    {i.symbol}
                  </option>
                ))}
              </Select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-muted-foreground">方向</span>
              <Select value={direction} onChange={(e) => setDirection(e.target.value as Direction | "")} className="w-32">
                <option value="">すべて</option>
                <option value="BUY">BUY</option>
                <option value="SELL">SELL</option>
              </Select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-muted-foreground">並び替え</span>
              <Select value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)} className="w-40">
                <option value="exit_time">決済日時</option>
                <option value="entry_time">エントリー日時</option>
                <option value="pnl">損益</option>
                <option value="pair">通貨ペア</option>
              </Select>
            </label>
            <Button type="button" variant="outline" size="default" onClick={() => setSortDesc((d) => !d)}>
              {sortDesc ? <ArrowDownAZ size={16} /> : <ArrowUpAZ size={16} />}
              {sortDesc ? "降順" : "昇順"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="text-xs font-medium text-muted-foreground">件数</div>
          <div className="mt-1 text-xl font-semibold tabular-nums">{sorted.length}</div>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="text-xs font-medium text-muted-foreground">合計損益</div>
          <div className={`mt-1 text-xl font-semibold tabular-nums ${totalPnl >= 0 ? "text-buy" : "text-sell"}`}>
            {totalPnl.toLocaleString("ja-JP", { maximumFractionDigits: 0 })}
          </div>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="text-xs font-medium text-muted-foreground">勝率</div>
          <div className="mt-1 text-xl font-semibold tabular-nums">
            {sorted.length ? `${((wins / sorted.length) * 100).toFixed(1)}%` : "—"}
          </div>
        </div>
      </div>

      <TradesTable trades={sorted} isLoading={isLoading} />
    </div>
  );
}
