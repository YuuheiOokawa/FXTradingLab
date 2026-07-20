import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ReasonList } from "@/components/signals/reason-list";
import { cn, formatPnl } from "@/lib/utils";
import type { ReplayDecisionRecord } from "@/types/api";

const ACTION_LABEL: Record<ReplayDecisionRecord["action"], string> = {
  BUY: "買い",
  SELL: "売り",
  SKIP: "見送り",
};

function actionVariant(action: ReplayDecisionRecord["action"]): "buy" | "sell" | "muted" {
  if (action === "BUY") return "buy";
  if (action === "SELL") return "sell";
  return "muted";
}

export function DecisionLog({ decisions, showExplanation }: { decisions: ReplayDecisionRecord[]; showExplanation: boolean }) {
  if (decisions.length === 0) {
    return <p className="text-sm text-muted-foreground">まだ判断がありません。</p>;
  }

  const reversed = [...decisions].reverse();

  return (
    <div className="space-y-3">
      {reversed.map((d, i) => {
        const isOpen = d.action !== "SKIP" && d.exit_price === null;
        return (
          <Card key={i}>
            <CardHeader className="flex-row items-center justify-between py-3">
              <div className="flex items-center gap-2">
                <Badge variant={actionVariant(d.action)}>{ACTION_LABEL[d.action]}</Badge>
                <CardTitle className="text-xs text-muted-foreground">index #{d.decided_at_index}</CardTitle>
              </div>
              {d.pnl !== null && (
                <span className={cn("text-sm font-semibold tabular-nums", d.pnl > 0 ? "text-buy" : d.pnl < 0 ? "text-sell" : "")}>
                  {formatPnl(d.pnl)}
                </span>
              )}
              {isOpen && <Badge variant="warning">オープン中</Badge>}
            </CardHeader>
            <CardContent className="space-y-3 pt-0">
              {d.action !== "SKIP" && (
                <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
                  <Field label="エントリー" value={d.entry_price?.toFixed(3) ?? "—"} />
                  <Field label="決済" value={d.exit_price?.toFixed(3) ?? "—"} />
                  <Field label="最大含み益" value={formatPnl(d.max_favorable)} />
                  <Field label="最大含み損" value={formatPnl(d.max_adverse)} />
                </div>
              )}
              {showExplanation && d.explanation && (
                <div>
                  <h4 className="mb-1.5 text-xs font-medium text-muted-foreground">ルール評価根拠</h4>
                  <ReasonList reasons={d.explanation} />
                </div>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-muted-foreground">{label}</div>
      <div className="font-medium tabular-nums">{value}</div>
    </div>
  );
}
