"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn, formatPnl, formatPrice } from "@/lib/utils";
import type { PaperPosition, PriceSnapshot } from "@/types/api";

function PnlCell({ position }: { position: PaperPosition }) {
  const { data: price } = useQuery<PriceSnapshot>({
    queryKey: ["price", position.instrument],
    queryFn: () => api.get(`/instruments/${position.instrument}/price`),
    refetchInterval: 5000,
  });

  if (!price) return <span className="text-muted-foreground">—</span>;

  const current = position.direction === "BUY" ? price.bid : price.ask;
  const distance = position.direction === "BUY" ? current - position.entry_price : position.entry_price - current;
  const pnl = distance * position.size;

  return <span className={cn("font-medium tabular-nums", pnl >= 0 ? "text-buy" : "text-sell")}>{formatPnl(pnl)}</span>;
}

function formatTime(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ja-JP", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function PositionsTable({ positions, isLoading }: { positions: PaperPosition[]; isLoading?: boolean }) {
  const queryClient = useQueryClient();

  const closeMutation = useMutation({
    mutationFn: (id: string) => api.post(`/paper/positions/${id}/close`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["paper-positions"] });
      queryClient.invalidateQueries({ queryKey: ["paper-account"] });
    },
  });

  if (isLoading) return <div className="p-4 text-sm text-muted-foreground">読み込み中...</div>;
  if (!positions.length) return <div className="p-4 text-sm text-muted-foreground">保有ポジションはありません</div>;

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
            <th className="px-3 py-2 font-medium">通貨ペア</th>
            <th className="px-3 py-2 font-medium">方向</th>
            <th className="px-3 py-2 font-medium">数量</th>
            <th className="px-3 py-2 font-medium">エントリー価格</th>
            <th className="px-3 py-2 font-medium">SL / TP</th>
            <th className="px-3 py-2 font-medium">評価損益</th>
            <th className="px-3 py-2 font-medium">建玉時刻</th>
            <th className="px-3 py-2 font-medium"></th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <tr key={p.id} className="border-b border-border last:border-0">
              <td className="px-3 py-2 font-medium">{p.instrument}</td>
              <td className="px-3 py-2">
                <Badge variant={p.direction === "BUY" ? "buy" : "sell"}>{p.direction}</Badge>
              </td>
              <td className="px-3 py-2 tabular-nums">{p.size.toLocaleString("ja-JP", { maximumFractionDigits: 0 })}</td>
              <td className="px-3 py-2 tabular-nums">{formatPrice(p.entry_price)}</td>
              <td className="px-3 py-2 tabular-nums text-xs text-muted-foreground">
                {formatPrice(p.stop_loss)} / {formatPrice(p.take_profit)}
              </td>
              <td className="px-3 py-2">
                <PnlCell position={p} />
              </td>
              <td className="px-3 py-2 text-xs text-muted-foreground">{formatTime(p.opened_at)}</td>
              <td className="px-3 py-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={closeMutation.isPending && closeMutation.variables === p.id}
                  onClick={() => closeMutation.mutate(p.id)}
                >
                  決済
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {closeMutation.isError && (
        <div className="border-t border-border p-2 text-xs text-sell">決済に失敗しました。再度お試しください。</div>
      )}
    </div>
  );
}
