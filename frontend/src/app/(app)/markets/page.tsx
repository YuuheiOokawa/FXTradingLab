"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AddInstrumentForm } from "@/components/markets/add-instrument-form";
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
