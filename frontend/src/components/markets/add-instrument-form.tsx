"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { Instrument } from "@/types/api";

export function AddInstrumentForm() {
  const [symbol, setSymbol] = useState("");
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (s: string) => api.post<Instrument>("/instruments", { symbol: s }),
    onSuccess: () => {
      setSymbol("");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["instruments"] });
    },
    onError: (err: unknown) => {
      setError(err instanceof ApiError ? err.message : "追加に失敗しました");
    },
  });

  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        const normalized = symbol.trim().toUpperCase();
        if (!normalized) return;
        mutation.mutate(normalized);
      }}
    >
      <div className="flex flex-col gap-1">
        <label htmlFor="add-symbol" className="text-xs text-muted-foreground">
          通貨ペアを追加 (例: GBP_USD)
        </label>
        <Input
          id="add-symbol"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          placeholder="USD_JPY"
          className="w-40"
        />
      </div>
      <Button type="submit" disabled={mutation.isPending || symbol.trim().length === 0}>
        {mutation.isPending ? "追加中..." : "追加"}
      </Button>
      {error && <span className="text-xs text-sell">{error}</span>}
    </form>
  );
}
