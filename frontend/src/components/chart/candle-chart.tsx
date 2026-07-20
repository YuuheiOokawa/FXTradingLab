"use client";

import { useEffect, useRef } from "react";
import {
  ColorType,
  createChart,
  CrosshairMode,
  type CandlestickData,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";

import type { Candle, SignalResponse } from "@/types/api";
import { bollingerBands, ema } from "./indicators";

function toTime(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;
}

function toLineData(times: UTCTimestamp[], values: (number | null)[]): LineData[] {
  const points: LineData[] = [];
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (v != null) points.push({ time: times[i] as Time, value: v });
  }
  return points;
}

const LEGEND = [
  { label: "EMA20", color: "#3b82f6" },
  { label: "EMA50", color: "#f97316" },
  { label: "EMA200", color: "#a855f7" },
];

export function CandleChart({
  candles,
  showBollinger,
  signal,
}: {
  candles: Candle[];
  showBollinger: boolean;
  signal: SignalResponse | null | undefined;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const ema20Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema50Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema200Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const bbUpperRef = useRef<ISeriesApi<"Line"> | null>(null);
  const bbLowerRef = useRef<ISeriesApi<"Line"> | null>(null);

  // Create the chart once on mount.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#9aa4b2" },
      grid: {
        vertLines: { color: "rgba(148,163,184,0.08)" },
        horzLines: { color: "rgba(148,163,184,0.08)" },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: "rgba(148,163,184,0.15)",
        rightOffset: 6,
      },
      rightPriceScale: { borderColor: "rgba(148,163,184,0.15)" },
      crosshair: { mode: CrosshairMode.Normal },
      autoSize: true,
      height: 420,
    });
    chartRef.current = chart;

    candleSeriesRef.current = chart.addCandlestickSeries({
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });

    ema20Ref.current = chart.addLineSeries({
      color: LEGEND[0].color,
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    ema50Ref.current = chart.addLineSeries({
      color: LEGEND[1].color,
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    ema200Ref.current = chart.addLineSeries({
      color: LEGEND[2].color,
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });

    bbUpperRef.current = chart.addLineSeries({
      color: "rgba(148,163,184,0.55)",
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    bbLowerRef.current = chart.addLineSeries({
      color: "rgba(148,163,184,0.55)",
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });

    return () => {
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      ema20Ref.current = null;
      ema50Ref.current = null;
      ema200Ref.current = null;
      bbUpperRef.current = null;
      bbLowerRef.current = null;
    };
  }, []);

  // Feed candle + EMA data whenever candles change.
  useEffect(() => {
    const candleSeries = candleSeriesRef.current;
    if (!candleSeries || candles.length === 0) return;

    const times = candles.map((c) => toTime(c.open_time));
    const closes = candles.map((c) => c.close);

    const candleData: CandlestickData[] = candles.map((c, i) => ({
      time: times[i] as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));
    candleSeries.setData(candleData);

    ema20Ref.current?.setData(toLineData(times, ema(closes, 20)));
    ema50Ref.current?.setData(toLineData(times, ema(closes, 50)));
    ema200Ref.current?.setData(toLineData(times, ema(closes, 200)));

    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  // Bollinger bands, toggleable.
  useEffect(() => {
    const upper = bbUpperRef.current;
    const lower = bbLowerRef.current;
    if (!upper || !lower) return;

    if (!showBollinger || candles.length === 0) {
      upper.setData([]);
      lower.setData([]);
      return;
    }

    const times = candles.map((c) => toTime(c.open_time));
    const closes = candles.map((c) => c.close);
    const { upper: u, lower: l } = bollingerBands(closes, 20, 2);
    upper.setData(toLineData(times, u));
    lower.setData(toLineData(times, l));
  }, [candles, showBollinger]);

  // Current signal marker on the latest bar.
  useEffect(() => {
    const candleSeries = candleSeriesRef.current;
    if (!candleSeries) return;

    if (!signal || candles.length === 0 || signal.label === "様子見") {
      candleSeries.setMarkers([]);
      return;
    }

    const last = candles[candles.length - 1];
    const isBuy = signal.direction === "BUY";
    const marker: SeriesMarker<Time> = {
      time: toTime(last.open_time) as Time,
      position: isBuy ? "belowBar" : "aboveBar",
      color: isBuy ? "#22c55e" : "#ef4444",
      shape: isBuy ? "arrowUp" : "arrowDown",
      text: isBuy ? "▲ BUY" : "▼ SELL",
    };
    candleSeries.setMarkers([marker]);
  }, [signal, candles]);

  return (
    <div className="relative rounded-lg border border-border bg-card">
      <div className="absolute left-3 top-2 z-10 flex flex-wrap gap-3 text-xs">
        {LEGEND.map((item) => (
          <span key={item.label} className="flex items-center gap-1.5 text-muted-foreground">
            <span className="inline-block h-0.5 w-3" style={{ backgroundColor: item.color }} />
            {item.label}
          </span>
        ))}
        {showBollinger && (
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <span className="inline-block h-0.5 w-3 bg-slate-400/60" />
            BB(20,2)
          </span>
        )}
      </div>
      <div ref={containerRef} className="h-[420px] w-full pt-2" />
      {candles.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">
          読み込み中...
        </div>
      )}
    </div>
  );
}
