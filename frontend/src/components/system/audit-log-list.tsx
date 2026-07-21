"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, ShieldCheck } from "lucide-react";

import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import type { AuditLogEntry } from "@/types/api";

const ACTION_LABEL: Record<string, string> = {
  login: "ログイン",
  logout: "ログアウト",
  kill_switch_on: "Kill Switch 有効化",
  kill_switch_off: "Kill Switch 解除",
  risk_setting_change: "リスク設定変更",
  live_trading_admin_enable: "LIVE取引 管理者許可 ON",
  live_trading_admin_disable: "LIVE取引 管理者許可 OFF",
  live_order_preview: "LIVE注文プレビュー",
  live_order_submit: "LIVE注文送信",
  live_order_reject: "LIVE注文拒否",
  live_order_result: "LIVE注文結果",
};

const SENSITIVE_ACTIONS = new Set(["kill_switch_on", "kill_switch_off", "live_trading_admin_enable", "live_order_submit"]);

function formatTime(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ja-JP", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function DiffRow({ entry }: { entry: AuditLogEntry }) {
  const [open, setOpen] = useState(false);
  const hasDetail = entry.before || entry.after || Object.keys(entry.context ?? {}).length > 0;

  return (
    <li className="rounded-md border border-border p-3">
      <button
        type="button"
        className="flex w-full items-start justify-between gap-3 text-left"
        onClick={() => hasDetail && setOpen((v) => !v)}
        disabled={!hasDetail}
      >
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {hasDetail && (open ? <ChevronDown size={14} className="shrink-0" /> : <ChevronRight size={14} className="shrink-0" />)}
            <span className="text-sm font-medium">{ACTION_LABEL[entry.action] ?? entry.action}</span>
            {SENSITIVE_ACTIONS.has(entry.action) && <Badge variant="warning">重要操作</Badge>}
          </div>
          <p className="mt-1 text-[11px] text-muted-foreground">{formatTime(entry.ts)} · {entry.actor}</p>
        </div>
      </button>
      {open && hasDetail && (
        <div className="mt-2 space-y-1 border-t border-border pt-2 text-xs">
          {entry.before && (
            <div>
              <span className="text-muted-foreground">変更前: </span>
              <code className="break-all">{JSON.stringify(entry.before)}</code>
            </div>
          )}
          {entry.after && (
            <div>
              <span className="text-muted-foreground">変更後: </span>
              <code className="break-all">{JSON.stringify(entry.after)}</code>
            </div>
          )}
          {entry.context && Object.keys(entry.context).length > 0 && (
            <div>
              <span className="text-muted-foreground">詳細: </span>
              <code className="break-all">{JSON.stringify(entry.context)}</code>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

/** docs/15_PRODUCTION_READINESS_REVIEW.md "Audit Log" — a reliable
 * who/when/what/before-after trail for the named sensitive actions
 * (login/logout, kill switch, risk settings, LIVE trading enablement, LIVE
 * order lifecycle). Distinct from the operational Notifications list above
 * it on this page. */
export function AuditLogList() {
  const { data, isLoading } = useQuery<AuditLogEntry[]>({
    queryKey: ["audit-log"],
    queryFn: () => api.get("/audit-log?limit=50"),
    refetchInterval: 10000,
  });

  const items = data ?? [];

  return (
    <div>
      <div className="mb-2 flex items-center gap-2 text-sm font-medium">
        <ShieldCheck size={16} className="text-muted-foreground" />
        監査ログ
      </div>
      {isLoading && <div className="p-4 text-sm text-muted-foreground">読み込み中...</div>}
      {!isLoading && !items.length && <div className="p-4 text-sm text-muted-foreground">記録された操作はありません</div>}
      <ul className="space-y-2">
        {items.map((entry) => (
          <DiffRow key={entry.id} entry={entry} />
        ))}
      </ul>
    </div>
  );
}
