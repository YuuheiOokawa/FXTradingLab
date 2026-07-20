"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RiskSettingsForm } from "@/components/settings/risk-settings-form";
import { LiveTradingGates } from "@/components/settings/live-trading-gates";
import type { RiskSettings } from "@/types/api";

export default function SettingsPage() {
  const { data, isLoading } = useQuery<RiskSettings>({
    queryKey: ["risk-settings"],
    queryFn: () => api.get("/settings/risk"),
  });

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold">設定</h1>
        <p className="mt-1 text-sm text-muted-foreground">リスク管理パラメータと動作モードを設定します。</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>リスク管理</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && <div className="text-sm text-muted-foreground">読み込み中...</div>}
          {data && <RiskSettingsForm settings={data} />}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>LIVE取引</CardTitle>
        </CardHeader>
        <CardContent>{data && <LiveTradingGates riskSettings={data} />}</CardContent>
      </Card>
    </div>
  );
}
