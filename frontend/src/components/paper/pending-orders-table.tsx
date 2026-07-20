"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatPrice } from "@/lib/utils";
import type { PaperOrderRecord } from "@/types/api";

const ORDER_TYPE_LABEL: Record<string, string> = {
  limit: "指値",
  stop: "逆指値",
};

export function PendingOrdersTable() {
  const queryClient = useQueryClient();

  const { data: orders, isLoading } = useQuery<PaperOrderRecord[]>({
    queryKey: ["paper-pending-orders"],
    queryFn: () => api.get("/paper/orders?status=pending"),
    refetchInterval: 5000,
  });

  const cancelMutation = useMutation({
    mutationFn: (orderId: string) => api.post(`/paper/orders/${orderId}/cancel`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["paper-pending-orders"] }),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>指値・逆指値注文（発注待ち）</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && <div className="text-sm text-muted-foreground">読み込み中...</div>}
        {!isLoading && (orders?.length ?? 0) === 0 && (
          <p className="text-sm text-muted-foreground">発注待ちの注文はありません。</p>
        )}
        {!isLoading && orders && orders.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="px-2 py-2 font-medium">通貨ペア</th>
                  <th className="px-2 py-2 font-medium">種別</th>
                  <th className="px-2 py-2 font-medium">方向</th>
                  <th className="px-2 py-2 font-medium">トリガー価格</th>
                  <th className="px-2 py-2 font-medium">数量</th>
                  <th className="px-2 py-2 font-medium" />
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.id} className="border-b border-border last:border-0">
                    <td className="px-2 py-2">{o.instrument}</td>
                    <td className="px-2 py-2">{ORDER_TYPE_LABEL[o.order_type] ?? o.order_type}</td>
                    <td className="px-2 py-2">
                      <span className={o.direction === "BUY" ? "text-buy" : "text-sell"}>
                        {o.direction === "BUY" ? "買い" : "売り"}
                      </span>
                    </td>
                    <td className="px-2 py-2 tabular-nums">{o.limit_price != null ? formatPrice(o.limit_price, 3) : "—"}</td>
                    <td className="px-2 py-2 tabular-nums">{o.size.toLocaleString("ja-JP")}</td>
                    <td className="px-2 py-2 text-right">
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        disabled={cancelMutation.isPending}
                        onClick={() => cancelMutation.mutate(o.id)}
                      >
                        <X size={14} /> 取消
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
