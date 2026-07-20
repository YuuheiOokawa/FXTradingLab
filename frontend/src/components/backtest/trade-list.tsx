"use client";

import { Fragment, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn, formatPnl, formatPrice } from "@/lib/utils";
import type { BacktestTrade } from "@/types/api";

function formatTime(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ja-JP", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

const REASON_TONE: Record<string, string> = {
  met: "text-buy",
  partial: "text-amber-500",
  failed: "text-muted-foreground",
};

export function TradeList({ trades, isLoading }: { trades: BacktestTrade[]; isLoading?: boolean }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (isLoading) {
    return <div className="p-4 text-sm text-muted-foreground">トレードを読み込み中...</div>;
  }
  if (!trades.length) {
    return <div className="p-4 text-sm text-muted-foreground">トレードがありません</div>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
            <th className="w-8 px-3 py-2"></th>
            <th className="px-3 py-2 font-medium">区分</th>
            <th className="px-3 py-2 font-medium">方向</th>
            <th className="px-3 py-2 font-medium">エントリー</th>
            <th className="px-3 py-2 font-medium">決済</th>
            <th className="px-3 py-2 font-medium">数量</th>
            <th className="px-3 py-2 font-medium">損益</th>
            <th className="px-3 py-2 font-medium">決済理由</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => {
            const isOpen = expanded === t.id;
            return (
              <Fragment key={t.id}>
                <tr
                  onClick={() => setExpanded(isOpen ? null : t.id)}
                  className="cursor-pointer border-b border-border last:border-0 hover:bg-muted/30"
                >
                  <td className="px-3 py-2 text-muted-foreground">
                    {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant={t.segment === "in_sample" ? "outline" : "muted"}>
                      {t.segment === "in_sample" ? "IS" : "OOS"}
                    </Badge>
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant={t.direction === "BUY" ? "buy" : "sell"}>{t.direction}</Badge>
                  </td>
                  <td className="px-3 py-2 tabular-nums">
                    {formatPrice(t.entry_price)}
                    <div className="text-xs text-muted-foreground">{formatTime(t.entry_time)}</div>
                  </td>
                  <td className="px-3 py-2 tabular-nums">
                    {formatPrice(t.exit_price)}
                    <div className="text-xs text-muted-foreground">{formatTime(t.exit_time)}</div>
                  </td>
                  <td className="px-3 py-2 tabular-nums">{t.size.toLocaleString("ja-JP", { maximumFractionDigits: 0 })}</td>
                  <td className={cn("px-3 py-2 tabular-nums font-medium", t.pnl >= 0 ? "text-buy" : "text-sell")}>
                    {formatPnl(t.pnl)}
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">{t.exit_reason}</td>
                </tr>
                {isOpen && (
                  <tr className="border-b border-border bg-muted/20 last:border-0">
                    <td></td>
                    <td colSpan={7} className="px-3 py-3">
                      <div className="grid gap-4 sm:grid-cols-2">
                        <div>
                          <div className="mb-1.5 text-xs font-semibold text-muted-foreground">
                            エントリー根拠 ({t.entry_reasons.reduce((s, r) => s + r.points, 0)}点)
                          </div>
                          <ul className="space-y-1">
                            {t.entry_reasons.map((r, i) => (
                              <li key={i} className={cn("flex items-start gap-1.5 text-xs", REASON_TONE[r.status])}>
                                <span className="mt-0.5 shrink-0 tabular-nums">
                                  {r.status === "met" ? "✓" : r.status === "partial" ? "△" : "✗"}
                                </span>
                                <span>
                                  {r.text} <span className="text-muted-foreground">({r.points}pt)</span>
                                </span>
                              </li>
                            ))}
                          </ul>
                        </div>
                        <div>
                          <div className="mb-1.5 text-xs font-semibold text-muted-foreground">決済理由</div>
                          <div className="text-xs">{t.exit_reason}</div>
                          <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                            <div>SL: {formatPrice(t.stop_loss)}</div>
                            <div>TP: {formatPrice(t.take_profit)}</div>
                          </div>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
