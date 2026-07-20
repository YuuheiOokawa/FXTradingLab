import { cn } from "@/lib/utils";
import type { SignalLabel } from "@/types/api";

const STYLES: Record<SignalLabel, string> = {
  強い買い: "bg-buy text-buy-foreground",
  買い: "bg-buy/20 text-buy",
  様子見: "bg-muted text-muted-foreground",
  売り: "bg-sell/20 text-sell",
  強い売り: "bg-sell text-sell-foreground",
};

export function SignalBadge({ label, className }: { label: SignalLabel; className?: string }) {
  return (
    <span className={cn("inline-flex items-center rounded-md px-2.5 py-1 text-sm font-semibold", STYLES[label], className)}>
      {label}
    </span>
  );
}
