import { Badge } from "@/components/ui/badge";
import type { TrendRegime, VolatilityRegime } from "@/types/api";

const TREND_LABEL: Record<TrendRegime, string> = {
  UPTREND: "上昇トレンド",
  DOWNTREND: "下降トレンド",
  RANGE: "レンジ",
  UNKNOWN: "不明",
};

const TREND_VARIANT: Record<TrendRegime, "buy" | "sell" | "muted" | "outline"> = {
  UPTREND: "buy",
  DOWNTREND: "sell",
  RANGE: "outline",
  UNKNOWN: "muted",
};

const VOL_LABEL: Record<VolatilityRegime, string> = {
  HIGH_VOLATILITY: "高ボラティリティ",
  LOW_VOLATILITY: "低ボラティリティ",
  NORMAL: "標準的ボラティリティ",
};

const VOL_VARIANT: Record<VolatilityRegime, "warning" | "outline" | "muted"> = {
  HIGH_VOLATILITY: "warning",
  LOW_VOLATILITY: "outline",
  NORMAL: "muted",
};

export function RegimeBadges({ trend, volatility }: { trend: TrendRegime; volatility: VolatilityRegime }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      <Badge variant={TREND_VARIANT[trend]}>{TREND_LABEL[trend]}</Badge>
      <Badge variant={VOL_VARIANT[volatility]}>{VOL_LABEL[volatility]}</Badge>
    </div>
  );
}
