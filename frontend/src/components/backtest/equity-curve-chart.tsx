"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

function formatTick(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ja-JP", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function EquityCurveChart({
  equityCurve,
  inSampleRatio,
}: {
  equityCurve: { time: string; equity: number }[];
  inSampleRatio: number;
}) {
  if (!equityCurve.length) {
    return <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">データがありません</div>;
  }

  const splitIndex = Math.max(0, Math.min(equityCurve.length - 1, Math.floor(equityCurve.length * inSampleRatio)));
  const splitTime = equityCurve[splitIndex]?.time;

  const chartData = equityCurve.map((pt, i) => ({
    time: pt.time,
    inSample: i <= splitIndex ? pt.equity : null,
    outSample: i >= splitIndex ? pt.equity : null,
  }));

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
          <XAxis
            dataKey="time"
            tickFormatter={formatTick}
            minTickGap={40}
            stroke="hsl(var(--muted-foreground))"
            fontSize={11}
          />
          <YAxis
            domain={["auto", "auto"]}
            stroke="hsl(var(--muted-foreground))"
            fontSize={11}
            width={70}
            tickFormatter={(v: number) => v.toLocaleString("ja-JP", { maximumFractionDigits: 0 })}
          />
          <Tooltip
            contentStyle={{
              background: "hsl(var(--card))",
              border: "1px solid hsl(var(--border))",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelFormatter={(v: string) => formatTick(v)}
            formatter={(value: number, name: string) => [
              value?.toLocaleString("ja-JP", { maximumFractionDigits: 0 }),
              name === "inSample" ? "In-Sample" : "Out-of-Sample",
            ]}
          />
          {splitTime && (
            <ReferenceLine
              x={splitTime}
              stroke="hsl(var(--muted-foreground))"
              strokeDasharray="4 4"
              label={{ value: "OOS開始", position: "insideTopRight", fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
            />
          )}
          <Line type="monotone" dataKey="inSample" stroke="hsl(var(--primary))" dot={false} strokeWidth={2} connectNulls />
          <Line type="monotone" dataKey="outSample" stroke="hsl(var(--sell))" dot={false} strokeWidth={2} connectNulls />
        </LineChart>
      </ResponsiveContainer>
      <div className="mt-2 flex items-center gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-primary" /> In-Sample (学習期間)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-sell" /> Out-of-Sample (検証期間)
        </span>
      </div>
    </div>
  );
}
