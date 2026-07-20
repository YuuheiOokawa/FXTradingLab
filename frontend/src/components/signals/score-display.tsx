import { cn } from "@/lib/utils";
import type { Direction } from "@/types/api";

/** Large "BUY SCORE 82/100" style headline display. */
export function ScoreDisplay({ direction, score }: { direction: Direction; score: number }) {
  const isBuy = direction === "BUY";
  return (
    <div className="flex items-baseline gap-3">
      <span
        className={cn(
          "text-xs font-bold tracking-widest uppercase rounded px-2 py-1",
          isBuy ? "bg-buy/15 text-buy" : "bg-sell/15 text-sell"
        )}
      >
        {isBuy ? "BUY SCORE" : "SELL SCORE"}
      </span>
      <span className={cn("text-4xl font-bold tabular-nums", isBuy ? "text-buy" : "text-sell")}>
        {score}
        <span className="text-lg text-muted-foreground font-normal">/100</span>
      </span>
    </div>
  );
}
