"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AuditLogList } from "@/components/system/audit-log-list";
import { KillSwitch } from "@/components/system/kill-switch";
import { StatusOverview } from "@/components/system/status-overview";
import { NotificationsList } from "@/components/system/notifications-list";
import type { SystemStatus } from "@/types/api";

export default function SystemPage() {
  const { data: status, isLoading } = useQuery<SystemStatus>({
    queryKey: ["system-status"],
    queryFn: () => api.get("/system/status"),
    refetchInterval: 5000,
  });

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold">システム</h1>
        <p className="mt-1 text-sm text-muted-foreground">システムの稼働状況、緊急停止、通知を管理します。</p>
      </div>

      {isLoading && <div className="text-sm text-muted-foreground">読み込み中...</div>}

      {status && (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="space-y-6">
            <KillSwitch status={status} />
            <Card>
              <CardHeader>
                <CardTitle>ステータス概要</CardTitle>
              </CardHeader>
              <CardContent>
                <StatusOverview status={status} />
              </CardContent>
            </Card>
          </div>

          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>通知</CardTitle>
              </CardHeader>
              <CardContent>
                <NotificationsList />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>監査ログ</CardTitle>
              </CardHeader>
              <CardContent>
                <AuditLogList />
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
