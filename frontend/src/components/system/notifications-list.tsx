"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, BellRing } from "lucide-react";

import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { NotificationItem } from "@/types/api";

function formatTime(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ja-JP", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function NotificationsList() {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery<NotificationItem[]>({
    queryKey: ["notifications"],
    queryFn: () => api.get("/notifications?unread_only=false"),
    refetchInterval: 5000,
  });

  const markRead = useMutation({
    mutationFn: (id: string) => api.post(`/notifications/${id}/read`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const items = data ?? [];
  const unreadCount = items.filter((n) => !n.is_read).length;

  return (
    <div>
      <div className="mb-2 flex items-center gap-2 text-sm font-medium">
        {unreadCount > 0 ? <BellRing size={16} className="text-primary" /> : <Bell size={16} className="text-muted-foreground" />}
        通知 {unreadCount > 0 && <Badge variant="default">{unreadCount}件未読</Badge>}
      </div>

      {isLoading && <div className="p-4 text-sm text-muted-foreground">読み込み中...</div>}
      {!isLoading && !items.length && <div className="p-4 text-sm text-muted-foreground">通知はありません</div>}

      <ul className="space-y-2">
        {items.map((n) => (
          <li
            key={n.id}
            className={cn(
              "flex items-start justify-between gap-3 rounded-md border border-border p-3",
              !n.is_read && "bg-primary/5"
            )}
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{n.title}</span>
                <Badge variant="muted">{n.kind}</Badge>
                <span className="text-[11px] text-muted-foreground">{n.channel}</span>
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">{n.body}</p>
              <p className="mt-1 text-[11px] text-muted-foreground">{formatTime(n.ts)}</p>
            </div>
            {!n.is_read && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={markRead.isPending && markRead.variables === n.id}
                onClick={() => markRead.mutate(n.id)}
                className="shrink-0"
              >
                既読にする
              </Button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
