"use client";

import { Pause, Play, SkipForward } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";

const SPEEDS = [1, 5, 10, 50];

export function ReplayControls({
  isAtEnd,
  autoplay,
  onToggleAutoplay,
  speed,
  onChangeSpeed,
  onStep,
  stepping,
  hasOpenDecision,
  onDecide,
  onClose,
  deciding,
  closing,
}: {
  isAtEnd: boolean;
  autoplay: boolean;
  onToggleAutoplay: () => void;
  speed: number;
  onChangeSpeed: (speed: number) => void;
  onStep: () => void;
  stepping: boolean;
  hasOpenDecision: boolean;
  onDecide: (action: "BUY" | "SELL" | "SKIP") => void;
  onClose: () => void;
  deciding: boolean;
  closing: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button variant="outline" size="sm" onClick={onStep} disabled={isAtEnd || stepping || autoplay}>
        <SkipForward size={14} /> 次のローソク足
      </Button>

      <Button variant={autoplay ? "secondary" : "outline"} size="sm" onClick={onToggleAutoplay} disabled={isAtEnd}>
        {autoplay ? (
          <>
            <Pause size={14} /> 一時停止
          </>
        ) : (
          <>
            <Play size={14} /> 自動再生
          </>
        )}
      </Button>

      <Select className="w-24" value={speed} onChange={(e) => onChangeSpeed(Number(e.target.value))}>
        {SPEEDS.map((s) => (
          <option key={s} value={s}>
            {s}x
          </option>
        ))}
      </Select>

      <div className="mx-2 h-6 w-px bg-border" />

      {hasOpenDecision ? (
        <Button variant="outline" size="sm" onClick={onClose} disabled={closing}>
          {closing ? "決済中..." : "決済"}
        </Button>
      ) : (
        <>
          <Button variant="buy" size="sm" onClick={() => onDecide("BUY")} disabled={deciding || isAtEnd}>
            BUY
          </Button>
          <Button variant="sell" size="sm" onClick={() => onDecide("SELL")} disabled={deciding || isAtEnd}>
            SELL
          </Button>
          <Button variant="ghost" size="sm" onClick={() => onDecide("SKIP")} disabled={deciding || isAtEnd}>
            見送り
          </Button>
        </>
      )}
    </div>
  );
}
