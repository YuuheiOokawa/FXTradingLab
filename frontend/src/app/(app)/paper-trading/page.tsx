"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AccountSummary } from "@/components/paper/account-summary";
import { OrderTicket } from "@/components/paper/order-ticket";
import { PendingOrdersTable } from "@/components/paper/pending-orders-table";
import { PositionsTable } from "@/components/paper/positions-table";
import type { PaperAccount, PaperPosition } from "@/types/api";

export default function PaperTradingPage() {
  const { data: account, isLoading: accountLoading } = useQuery<PaperAccount>({
    queryKey: ["paper-account"],
    queryFn: () => api.get("/paper/account"),
    refetchInterval: 5000,
  });

  const { data: positions, isLoading: positionsLoading } = useQuery<PaperPosition[]>({
    queryKey: ["paper-positions"],
    queryFn: () => api.get("/paper/positions"),
    refetchInterval: 5000,
  });

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold">Paper Trading</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          仮想資金でのリアルタイム取引。注文はリスクエンジンの審査を受けます（本番口座への発注は行われません）。
        </p>
      </div>

      {account && <AccountSummary account={account} />}
      {accountLoading && <div className="text-sm text-muted-foreground">口座情報を読み込み中...</div>}

      <div className="grid gap-6 lg:grid-cols-[380px_1fr]">
        <OrderTicket />

        <Card>
          <CardHeader>
            <CardTitle>保有ポジション</CardTitle>
          </CardHeader>
          <CardContent>
            <PositionsTable positions={positions ?? []} isLoading={positionsLoading} />
          </CardContent>
        </Card>
      </div>

      <PendingOrdersTable />
    </div>
  );
}
