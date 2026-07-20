"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { OrderTicket, type SimulationOrder } from "@/components/simulation/order-ticket";
import { ResultCard } from "@/components/simulation/result-card";
import { api } from "@/lib/api";
import type { SimulationState } from "@/types/api";

export default function SimulationPage() {
  const [activeIds, setActiveIds] = useState<string[]>([]);
  const queryClient = useQueryClient();

  const createMutation = useMutation({
    mutationFn: (order: SimulationOrder) => api.post<SimulationState>("/simulate", order),
    onSuccess: (sim) => {
      queryClient.setQueryData(["simulation", sim.id], sim);
      setActiveIds((prev) => [sim.id, ...prev]);
    },
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">シミュレーション</h1>
        <p className="text-sm text-muted-foreground">「もしここでエントリーしていたら」を検証する取引シミュレーター。</p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <OrderTicket onSubmit={(order) => createMutation.mutate(order)} submitting={createMutation.isPending} />

        <div className="space-y-4">
          {createMutation.isError && (
            <p className="text-sm text-sell">
              シミュレーションの発注に失敗しました: {(createMutation.error as Error).message}
            </p>
          )}
          {activeIds.length === 0 && (
            <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
              左のフォームからシミュレーションを開始してください。
            </div>
          )}
          {activeIds.map((id) => (
            <ResultCard key={id} id={id} />
          ))}
        </div>
      </div>
    </div>
  );
}
