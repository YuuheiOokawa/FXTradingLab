"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AddInstrumentForm } from "@/components/markets/add-instrument-form";
import { CalibrationPanel } from "@/components/markets/calibration-panel";
import { InstrumentTable } from "@/components/markets/instrument-table";
import type { Instrument } from "@/types/api";

export default function MarketsPage() {
  const { data: instruments, isLoading } = useQuery<Instrument[]>({
    queryKey: ["instruments"],
    queryFn: () => api.get("/instruments"),
  });

  const watched = (instruments ?? []).filter((i) => i.is_watched);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold text-foreground">マーケット</h1>
        <p className="text-sm text-muted-foreground">監視中の通貨ペアのリアルタイムレートと管理</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>通貨ペアの追加</CardTitle>
        </CardHeader>
        <CardContent>
          <AddInstrumentForm />
        </CardContent>
      </Card>

      {/* A newly added pair should not inherit whichever strategy happened to be
          written first — that is exactly what lost money over 23 years. */}
      <Card>
        <CardHeader>
          <CardTitle>値動きの性格診断（どの戦略が向くか）</CardTitle>
        </CardHeader>
        <CardContent>
          <CalibrationPanel symbols={watched.map((i) => i.symbol)} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>監視通貨ペア一覧</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">読み込み中...</p>
          ) : (
            <InstrumentTable instruments={watched} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
