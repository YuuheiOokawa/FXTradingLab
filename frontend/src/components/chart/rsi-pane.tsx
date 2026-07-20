"use client";

import { useEffect, useRef } from "react";
import {
  ColorType,
  createChart,
  LineStyle,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type LineData,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";

import type { Candle } from "@/types/api";
import { rsi } from "./indicators";

function toTime(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;
}

export function RsiPane({ candles }: { candles: Candle[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const upperLineRef = useRef<IPriceLine | null>(null);
  const lowerLineRef = useRef<IPriceLine | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#9aa4b2" },
      grid: {
        vertLines: { color: "rgba(148,163,184,0.08)" },
        horzLines: { color: "rgba(148,163,184,0.08)" },
      },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: "rgba(148,163,184,0.15)" },
      rightPriceScale: { borderColor: "rgba(148,163,184,0.15)" },
      autoSize: true,
      height: 120,
    });
    chartRef.current = chart;

    const series = chart.addLineSeries({
      color: "#38bdf8",
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: true,
      autoscaleInfoProvider: () => ({
        priceRange: { minValue: 0, maxValue: 100 },
      }),
    });
    seriesRef.current = series;

    upperLineRef.current = series.createPriceLine({
      price: 70,
      color: "rgba(239,68,68,0.5)",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: "70",
    });
    lowerLineRef.current = series.createPriceLine({
      price: 30,
      color: "rgba(34,197,94,0.5)",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: "30",
    });

    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      upperLineRef.current = null;
      lowerLineRef.current = null;
    };
  }, []);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series || candles.length === 0) return;

    const times = candles.map((c) => toTime(c.open_time));
    const closes = candles.map((c) => c.close);
    const values = rsi(closes, 14);

    const data: LineData[] = [];
    for (let i = 0; i < values.length; i++) {
      const v = values[i];
      if (v != null) data.push({ time: times[i] as Time, value: v });
    }
    series.setData(data);
    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  return (
    <div className="relative rounded-lg border border-border bg-card">
      <div className="absolute left-3 top-1 z-10 text-xs text-muted-foreground">RSI(14)</div>
      <div ref={containerRef} className="h-[120px] w-full" />
    </div>
  );
}
