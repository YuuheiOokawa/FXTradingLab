"use client";

import { useState } from "react";

import { Select } from "@/components/ui/select";
import { SignalCard } from "@/components/signals/signal-card";
import { SignalDetail } from "@/components/signals/signal-detail";
import type { Granularity } from "@/types/api";

const WATCHLIST = ["USD_JPY", "EUR_JPY", "GBP_JPY", "EUR_USD"];
const GRANULARITIES: Granularity[] = ["M1", "M5", "M15", "H1", "H4", "D"];

export default function SignalsPage() {
  const [granularity, setGranularity] = useState<Granularity>("M15");
  const [selected, setSelected] = useState<string>(WATCHLIST[0]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">シグナル</h1>
          <p className="text-sm text-muted-foreground">なぜ今は買い/売りなのか — 根拠を全条件で確認できます。</p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-muted-foreground" htmlFor="granularity-select">
            時間足
          </label>
          <Select
            id="granularity-select"
            className="w-28"
            value={granularity}
            onChange={(e) => setGranularity(e.target.value as Granularity)}
          >
            {GRANULARITIES.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </Select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {WATCHLIST.map((instrument) => (
          <SignalCard
            key={instrument}
            instrument={instrument}
            granularity={granularity}
            selected={selected === instrument}
            onSelect={() => setSelected(instrument)}
          />
        ))}
      </div>

      <SignalDetail instrument={selected} granularity={granularity} />
    </div>
  );
}
