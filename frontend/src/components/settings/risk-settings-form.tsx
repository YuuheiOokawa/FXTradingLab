"use client";

import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { RiskSettings } from "@/types/api";

const AUTO_MODE_INFO: Record<RiskSettings["auto_mode"], string> = {
  manual: "MANUAL — シグナルは表示のみ。発注はすべて手動で行います。",
  semi_auto: "SEMI_AUTO — シグナル発生時に確認ダイアログを表示し、承認後に発注します。",
  full_auto: "FULL_AUTO — リスク上限内であれば人の確認なしに自動発注します（本ビルドでは実発注は未実装）。",
};

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {children}
      {hint && <span className="text-[11px] text-muted-foreground">{hint}</span>}
    </label>
  );
}

export function RiskSettingsForm({ settings }: { settings: RiskSettings }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<RiskSettings>(settings);
  const [saved, setSaved] = useState(false);

  useEffect(() => setForm(settings), [settings]);

  const mutation = useMutation<RiskSettings, Error, Partial<RiskSettings>>({
    mutationFn: (body) => api.put<RiskSettings>("/settings/risk", body),
    onSuccess: (data) => {
      queryClient.setQueryData(["risk-settings"], data);
      setForm(data);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    },
  });

  function set<K extends keyof RiskSettings>(key: K, value: RiskSettings[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const { kill_switch_active, live_trading_admin_enabled, ...rest } = form;
    void kill_switch_active;
    void live_trading_admin_enabled;
    mutation.mutate(rest);
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <Field label="1トレード最大リスク%" hint="資金に対する割合">
          <Input
            type="number"
            min={0.1}
            max={20}
            step={0.1}
            value={form.max_risk_per_trade_pct}
            onChange={(e) => set("max_risk_per_trade_pct", Number(e.target.value))}
          />
        </Field>
        <Field label="1日の最大損失%">
          <Input
            type="number"
            min={0.1}
            max={50}
            step={0.1}
            value={form.max_daily_loss_pct}
            onChange={(e) => set("max_daily_loss_pct", Number(e.target.value))}
          />
        </Field>
        <Field label="最大ドローダウン%">
          <Input
            type="number"
            min={0.1}
            max={90}
            step={0.5}
            value={form.max_drawdown_pct}
            onChange={(e) => set("max_drawdown_pct", Number(e.target.value))}
          />
        </Field>
        <Field label="最大同時ポジション数">
          <Input
            type="number"
            min={1}
            max={50}
            step={1}
            value={form.max_concurrent_positions}
            onChange={(e) => set("max_concurrent_positions", Number(e.target.value))}
          />
        </Field>
        <Field label="同一銘柄の最大ポジション数">
          <Input
            type="number"
            min={1}
            max={20}
            step={1}
            value={form.max_same_symbol_positions}
            onChange={(e) => set("max_same_symbol_positions", Number(e.target.value))}
          />
        </Field>
        <Field label="連敗停止回数" hint="この回数連敗したら自動停止">
          <Input
            type="number"
            min={1}
            max={20}
            step={1}
            value={form.consecutive_loss_stop_count}
            onChange={(e) => set("consecutive_loss_stop_count", Number(e.target.value))}
          />
        </Field>
        <Field label="許容スプレッド上限 (pips)">
          <Input
            type="number"
            min={0}
            max={50}
            step={0.1}
            value={form.max_spread_pips_default}
            onChange={(e) => set("max_spread_pips_default", Number(e.target.value))}
          />
        </Field>
      </div>

      <div>
        <Field label="動作モード (auto_mode)">
          <Select value={form.auto_mode} onChange={(e) => set("auto_mode", e.target.value as RiskSettings["auto_mode"])} className="max-w-xs">
            <option value="manual">MANUAL（手動）</option>
            <option value="semi_auto">SEMI_AUTO（半自動・要承認）</option>
            <option value="full_auto">FULL_AUTO（全自動）</option>
          </Select>
        </Field>
        <p className="mt-1.5 text-xs text-muted-foreground">{AUTO_MODE_INFO[form.auto_mode]}</p>
      </div>

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? "保存中..." : "リスク設定を保存"}
        </Button>
        {saved && (
          <span className="flex items-center gap-1 text-xs text-buy">
            <CheckCircle2 size={14} /> 保存しました
          </span>
        )}
        {mutation.isError && <span className="text-xs text-sell">保存に失敗しました</span>}
      </div>
    </form>
  );
}
