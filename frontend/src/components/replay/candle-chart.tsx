"use client";

import { useEffect, useRef } from "react";

import type { Candle } from "@/types/api";

/** Lightweight self-contained canvas candlestick renderer for the replay
 * page. Draws only the currently revealed candles, so the "future" stays
 * hidden as the trainee steps forward. */
export function CandleChart({ candles, height = 360 }: { candles: Candle[]; height?: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const dpr = window.devicePixelRatio || 1;
    const width = container.clientWidth;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);

    if (candles.length === 0) {
      ctx.fillStyle = "hsl(var(--muted-foreground))";
      ctx.font = "13px sans-serif";
      ctx.fillText("ローソク足データがありません", 12, height / 2);
      return;
    }

    const padding = { top: 10, right: 56, bottom: 20, left: 4 };
    const plotWidth = width - padding.left - padding.right;
    const plotHeight = height - padding.top - padding.bottom;

    const high = Math.max(...candles.map((c) => c.high));
    const low = Math.min(...candles.map((c) => c.low));
    const range = high - low || 1;

    const yFor = (price: number) => padding.top + (1 - (price - low) / range) * plotHeight;

    const candleWidth = plotWidth / candles.length;
    const bodyWidth = Math.max(1, candleWidth * 0.6);

    // gridlines + price labels
    ctx.strokeStyle = "hsl(var(--border))";
    ctx.fillStyle = "hsl(var(--muted-foreground))";
    ctx.font = "10px sans-serif";
    ctx.lineWidth = 1;
    const gridLines = 4;
    for (let i = 0; i <= gridLines; i++) {
      const price = low + (range * i) / gridLines;
      const y = yFor(price);
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(width - padding.right, y);
      ctx.stroke();
      ctx.fillText(price.toFixed(3), width - padding.right + 6, y + 3);
    }

    candles.forEach((c, i) => {
      const x = padding.left + i * candleWidth + candleWidth / 2;
      const up = c.close >= c.open;
      ctx.strokeStyle = ctx.fillStyle = up ? "hsl(var(--buy))" : "hsl(var(--sell))";

      ctx.beginPath();
      ctx.moveTo(x, yFor(c.high));
      ctx.lineTo(x, yFor(c.low));
      ctx.stroke();

      const openY = yFor(c.open);
      const closeY = yFor(c.close);
      const top = Math.min(openY, closeY);
      const h = Math.max(1, Math.abs(closeY - openY));
      ctx.fillRect(x - bodyWidth / 2, top, bodyWidth, h);
    });
  }, [candles, height]);

  return (
    <div ref={containerRef} className="w-full">
      <canvas ref={canvasRef} />
    </div>
  );
}
