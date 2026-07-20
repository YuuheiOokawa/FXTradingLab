import { Check, Minus, X } from "lucide-react";

import { cn } from "@/lib/utils";
import type { SignalReason } from "@/types/api";

const STATUS_ICON: Record<SignalReason["status"], typeof Check> = {
  met: Check,
  partial: Minus,
  failed: X,
};

const STATUS_STYLE: Record<SignalReason["status"], string> = {
  met: "text-buy",
  partial: "text-amber-500",
  failed: "text-sell",
};

/** Itemized ✓/△/✗ breakdown of why a signal scored the way it did — the
 * app's core "なぜ今は買いなのか" explainability feature. */
export function ReasonList({ reasons }: { reasons: SignalReason[] }) {
  if (reasons.length === 0) {
    return <p className="text-sm text-muted-foreground">根拠データがありません。</p>;
  }
  return (
    <ul className="space-y-1.5">
      {reasons.map((reason, i) => {
        const Icon = STATUS_ICON[reason.status];
        return (
          <li key={i} className="flex items-start gap-2 text-sm">
            <Icon size={16} className={cn("mt-0.5 shrink-0", STATUS_STYLE[reason.status])} />
            <span className="flex-1 text-foreground">{reason.text}</span>
            <span className={cn("shrink-0 tabular-nums font-mono text-xs", STATUS_STYLE[reason.status])}>
              {reason.points > 0 ? "+" : ""}
              {reason.points}pt
            </span>
          </li>
        );
      })}
    </ul>
  );
}
