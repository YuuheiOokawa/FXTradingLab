"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SummaryStats } from "@/components/dashboard/summary-stats";
import { WatchlistSection } from "@/components/dashboard/watchlist-section";
import { RecentSignals } from "@/components/dashboard/recent-signals";
import { RecentTrades } from "@/components/dashboard/recent-trades";
import { PositionsList } from "@/components/dashboard/positions-list";
import { SystemPanel } from "@/components/dashboard/system-panel";
import { computeJournalStats } from "@/components/dashboard/metrics";
import type { Instrument, PaperAccount, PaperPosition, SystemStatus, TradeJournalEntry } from "@/types/api";

export default function DashboardPage() {
  const { data: instruments, isLoading: instrumentsLoading, isError: instrumentsError } = useQuery<Instrument[]>({
    queryKey: ["instruments"],
    queryFn: () => api.get("/instruments"),
  });

  const { data: account, isLoading: accountLoading } = useQuery<PaperAccount>({
    queryKey: ["paper-account"],
    queryFn: () => api.get("/paper/account"),
    refetchInterval: 15000,
  });

  const { data: positions } = useQuery<PaperPosition[]>({
    queryKey: ["paper-positions"],
    queryFn: () => api.get("/paper/positions"),
    refetchInterval: 15000,
  });

  const { data: trades } = useQuery<TradeJournalEntry[]>({
    queryKey: ["journal-trades", 50],
    queryFn: () => api.get("/journal/trades?limit=50"),
    refetchInterval: 30000,
  });

  const { data: systemStatus } = useQuery<SystemStatus>({
    queryKey: ["system-status"],
    queryFn: () => api.get("/system/status"),
    refetchInterval: 5000,
  });

  const watched = (instruments ?? []).filter((i) => i.is_watched);
  const stats = computeJournalStats(trades ?? [], account);
  const initialLoading = instrumentsLoading && accountLoading;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold text-foreground">ダッシュボード</h1>
        <p className="text-sm text-muted-foreground">口座状況・監視銘柄・シグナル・システム稼働状態の概要</p>
      </div>

      {initialLoading && (
        <div className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">読み込み中...</div>
      )}
      {!initialLoading && instrumentsError && (
        <div className="rounded-lg border border-sell/30 bg-sell/10 p-4 text-sm text-sell">
          データの取得に失敗しました。しばらくしてから再読み込みしてください。
        </div>
      )}

      {!initialLoading && (
      <>
      <section>
        <SummaryStats account={account} positions={positions} stats={stats} />
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-foreground">監視通貨ペア</h2>
        <WatchlistSection instruments={watched} />
      </section>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>現在ポジション</CardTitle>
          </CardHeader>
          <CardContent>
            <PositionsList positions={positions ?? []} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>直近の売買シグナル</CardTitle>
          </CardHeader>
          <CardContent>
            <RecentSignals instruments={watched} />
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>最近のトレード</CardTitle>
        </CardHeader>
        <CardContent>
          <RecentTrades trades={trades ?? []} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>システム稼働状態</CardTitle>
        </CardHeader>
        <CardContent>
          <SystemPanel status={systemStatus} />
        </CardContent>
      </Card>
      </>
      )}
    </div>
  );
}
