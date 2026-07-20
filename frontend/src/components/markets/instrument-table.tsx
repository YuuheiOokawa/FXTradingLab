"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { InstrumentRow } from "./instrument-row";
import type { Instrument } from "@/types/api";

export function InstrumentTable({ instruments }: { instruments: Instrument[] }) {
  const queryClient = useQueryClient();

  const removeMutation = useMutation({
    mutationFn: (symbol: string) => api.delete(`/instruments/${symbol}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["instruments"] });
    },
  });

  if (instruments.length === 0) {
    return <p className="text-sm text-muted-foreground">監視中の通貨ペアはありません。上のフォームから追加してください。</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-muted-foreground">
            <th className="py-2 pr-4 font-medium">通貨ペア</th>
            <th className="py-2 pr-4 font-medium">状態</th>
            <th className="py-2 pr-4 font-medium">Bid</th>
            <th className="py-2 pr-4 font-medium">Ask</th>
            <th className="py-2 pr-4 font-medium">Mid</th>
            <th className="py-2 pr-4 font-medium">Spread</th>
            <th className="py-2 pr-4 font-medium">高値</th>
            <th className="py-2 pr-4 font-medium">安値</th>
            <th className="py-2 pr-4 font-medium">前日比</th>
            <th className="py-2 text-right font-medium">操作</th>
          </tr>
        </thead>
        <tbody>
          {instruments.map((inst) => (
            <InstrumentRow
              key={inst.symbol}
              instrument={inst}
              onRemove={(symbol) => removeMutation.mutate(symbol)}
              removing={removeMutation.isPending && removeMutation.variables === inst.symbol}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}
