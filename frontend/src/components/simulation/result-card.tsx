"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { cn, formatPnl } from "@/lib/utils";
import type { SimulationState } from "@/types/api";

const STATUS_LABEL: Record<SimulationState["status"], string> = {
  open: "オープン中",
  closed_tp: "利確決済 (TP)",
  closed_sl: "損切り決済 (SL)",
  closed_manual: "手動決済",
};

function statusVariant(status: SimulationState["status"]): "buy" | "sell" | "muted" {
  if (status === "closed_tp") return "buy";
  if (status === "closed_sl") return "sell";
  return "muted";
}

export function ResultCard({ id, onClosed }: { id: string; onClosed?: () => void }) {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery<SimulationState>({
    queryKey: ["simulation", id],
    queryFn: () => api.get(`/simulate/${id}`),
    refetchInterval: (query) => (query.state.data?.status === "open" ? 2000 : false),
  });

  const closeMutation = useMutation({
    mutationFn: () => api.post<SimulationState>(`/simulate/${id}/close`),
    onSuccess: (updated) => {
      queryClient.setQueryData(["simulation", id], updated);
      onClosed?.();
    },
  });

  if (isLoading || !data) {
    return (
      <Card>
        <CardContent className="p-6 text-sm text-muted-foreground">読み込み中...</CardContent>
      </Card>
    );
  }

  const isBuy = data.direction === "BUY";
  const isOpen = data.status === "open";
  const pnlPositive = data.current_pnl > 0;

  return (
    <Card className={cn(!isOpen && "border-muted")}>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="text-base text-foreground font-semibold">
          {data.instrument.replace("_", "/")}{" "}
          <span className={cn("font-normal", isBuy ? "text-buy" : "text-sell")}>{isBuy ? "買い" : "売り"}</span>
        </CardTitle>
        <Badge variant={statusVariant(data.status)}>{STATUS_LABEL[data.status]}</Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <div className="text-xs text-muted-foreground">評価損益</div>
          <div className={cn("text-3xl font-bold tabular-nums", pnlPositive ? "text-buy" : data.current_pnl < 0 ? "text-sell" : "")}>
            {formatPnl(data.current_pnl)}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <Field label="エントリー" value={data.entry_price.toFixed(3)} />
          <Field label={isOpen ? "現在価格" : "決済価格"} value={(isOpen ? data.current_price : data.closed_price ?? data.current_price).toFixed(3)} />
          <Field label="SL / TP" value={`${data.stop_loss.toFixed(3)} / ${data.take_profit.toFixed(3)}`} />
          <Field label="R/R" value={`1 : ${data.risk_reward_ratio.toFixed(2)}`} />
          <Field label="最大含み益" value={formatPnl(data.max_favorable)} valueClassName="text-buy" />
          <Field label="最大含み損" value={formatPnl(data.max_adverse)} valueClassName="text-sell" />
          <Field label="数量" value={data.size.toLocaleString("ja-JP")} />
        </div>

        {isOpen && (
          <Button variant="outline" className="w-full" onClick={() => closeMutation.mutate()} disabled={closeMutation.isPending}>
            {closeMutation.isPending ? "決済中..." : "手動決済"}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function Field({ label, value, valueClassName }: { label: string; value: string; valueClassName?: string }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn("font-medium tabular-nums", valueClassName)}>{value}</div>
    </div>
  );
}
