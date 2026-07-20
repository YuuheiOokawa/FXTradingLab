"use client";

import { useEffect, useRef } from "react";
import {
  ColorType,
  createChart,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";

import type { Candle } from "@/types/api";
import { macd } from "./indicators";

function toTime(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;
}

export function MacdPane({ candles }: { candles: Candle[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const macdSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const signalSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const histSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);

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

    histSeriesRef.current = chart.addHistogramSeries({
      priceLineVisible: false,
      lastValueVisible: false,
      base: 0,
    });
    macdSeriesRef.current = chart.addLineSeries({
      color: "#3b82f6",
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerVisible: false,
    });
    signalSeriesRef.current = chart.addLineSeries({
      color: "#f97316",
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });

    return () => {
      chart.remove();
      chartRef.current = null;
      macdSeriesRef.current = null;
      signalSeriesRef.current = null;
      histSeriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    const macdSeries = macdSeriesRef.current;
    const signalSeries = signalSeriesRef.current;
    const histSeries = histSeriesRef.current;
    if (!macdSeries || !signalSeries || !histSeries || candles.length === 0) return;

    const times = candles.map((c) => toTime(c.open_time));
    const closes = candles.map((c) => c.close);
    const { macdLine, signalLine, histogram } = macd(closes, 12, 26, 9);

    const macdData: LineData[] = [];
    const signalData: LineData[] = [];
    const histData: HistogramData[] = [];
    for (let i = 0; i < closes.length; i++) {
      const time = times[i] as Time;
      const m = macdLine[i];
      const s = signalLine[i];
      const h = histogram[i];
      if (m != null) macdData.push({ time, value: m });
      if (s != null) signalData.push({ time, value: s });
      if (h != null) histData.push({ time, value: h, color: h >= 0 ? "rgba(34,197,94,0.6)" : "rgba(239,68,68,0.6)" });
    }
    macdSeries.setData(macdData);
    signalSeries.setData(signalData);
    histSeries.setData(histData);
    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  return (
    <div className="relative rounded-lg border border-border bg-card">
      <div className="absolute left-3 top-1 z-10 flex gap-3 text-xs text-muted-foreground">
        <span>MACD(12,26,9)</span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-0.5 w-3 bg-[#3b82f6]" /> MACD
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-0.5 w-3 bg-[#f97316]" /> Signal
        </span>
      </div>
      <div ref={containerRef} className="h-[120px] w-full" />
    </div>
  );
}
