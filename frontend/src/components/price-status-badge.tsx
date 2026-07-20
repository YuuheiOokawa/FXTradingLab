import { Wifi, WifiOff, AlertTriangle, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import type { PriceStatus } from "@/hooks/useLivePriceStatus";

const CONFIG: Record<PriceStatus, { label: string; icon: typeof Wifi; className: string }> = {
  live: { label: "LIVE", icon: Wifi, className: "text-buy" },
  stale: { label: "STALE", icon: AlertTriangle, className: "text-amber-500" },
  disconnected: { label: "DISCONNECTED", icon: WifiOff, className: "text-sell" },
  connecting: { label: "接続中…", icon: Loader2, className: "text-muted-foreground" },
};

/** Never show a stale price as if it were live — see useLivePriceStatus.ts. */
export function PriceStatusBadge({ status, className }: { status: PriceStatus; className?: string }) {
  const { label, icon: Icon, className: toneClass } = CONFIG[status];
  return (
    <span className={cn("inline-flex items-center gap-1 text-[10px] font-semibold tracking-wide", toneClass, className)}>
      <Icon size={10} className={status === "connecting" ? "animate-spin" : undefined} />
      {label}
    </span>
  );
}
