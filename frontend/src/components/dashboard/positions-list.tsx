import { Badge } from "@/components/ui/badge";
import { formatPrice } from "@/lib/utils";
import type { PaperPosition } from "@/types/api";

export function PositionsList({ positions }: { positions: PaperPosition[] }) {
  if (positions.length === 0) {
    return <p className="text-sm text-muted-foreground">現在保有中のポジションはありません。</p>;
  }
  return (
    <ul className="divide-y divide-border">
      {positions.map((p) => (
        <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
          <div className="flex items-center gap-3">
            <span className="font-medium text-foreground">{p.instrument}</span>
            <Badge variant={p.direction === "BUY" ? "buy" : "sell"}>{p.direction === "BUY" ? "買い" : "売り"}</Badge>
          </div>
          <div className="flex flex-wrap items-center gap-4 text-xs tabular-nums text-muted-foreground">
            <span>数量 {p.size}</span>
            <span>建値 {formatPrice(p.entry_price, 3)}</span>
            {p.stop_loss !== null && <span>SL {formatPrice(p.stop_loss, 3)}</span>}
            {p.take_profit !== null && <span>TP {formatPrice(p.take_profit, 3)}</span>}
            <span>{new Date(p.opened_at).toLocaleString("ja-JP")}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}
