"use client";

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { WinRateBreakdown } from "@/types/api";

export function WinRateChart({
  breakdown,
  metric,
}: {
  breakdown: WinRateBreakdown["breakdown"];
  metric: "win_rate_pct" | "total_pnl";
}) {
  if (!breakdown.length) {
    return <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">データがありません</div>;
  }

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={breakdown} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
          <XAxis dataKey="key" stroke="hsl(var(--muted-foreground))" fontSize={11} />
          <YAxis
            stroke="hsl(var(--muted-foreground))"
            fontSize={11}
            width={metric === "win_rate_pct" ? 40 : 70}
            tickFormatter={(v: number) =>
              metric === "win_rate_pct" ? `${v}%` : v.toLocaleString("ja-JP", { maximumFractionDigits: 0 })
            }
          />
          <Tooltip
            contentStyle={{
              background: "hsl(var(--card))",
              border: "1px solid hsl(var(--border))",
              borderRadius: 8,
              fontSize: 12,
            }}
            formatter={(value: number) => [
              metric === "win_rate_pct" ? `${value.toFixed(1)}%` : value.toLocaleString("ja-JP", { maximumFractionDigits: 0 }),
              metric === "win_rate_pct" ? "勝率" : "合計損益",
            ]}
          />
          <Bar dataKey={metric} radius={[4, 4, 0, 0]}>
            {breakdown.map((b, i) => (
              <Cell
                key={i}
                fill={
                  metric === "win_rate_pct"
                    ? b.win_rate_pct >= 50
                      ? "hsl(var(--buy))"
                      : "hsl(var(--sell))"
                    : b.total_pnl >= 0
                      ? "hsl(var(--buy))"
                      : "hsl(var(--sell))"
                }
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
