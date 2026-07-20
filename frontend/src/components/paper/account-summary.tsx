import { StatTile } from "@/components/ui/stat-tile";
import type { PaperAccount } from "@/types/api";

export function AccountSummary({ account }: { account: PaperAccount }) {
  const drawdownFromPeak =
    account.high_water_mark > 0 ? ((account.balance - account.high_water_mark) / account.high_water_mark) * 100 : 0;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <StatTile
        label="残高"
        value={`${account.balance.toLocaleString("ja-JP", { maximumFractionDigits: 0 })} ${account.currency}`}
      />
      <StatTile
        label="最高残高 (High Water Mark)"
        value={`${account.high_water_mark.toLocaleString("ja-JP", { maximumFractionDigits: 0 })} ${account.currency}`}
      />
      <StatTile
        label="ピークからの変動"
        value={`${drawdownFromPeak.toFixed(2)}%`}
        tone={drawdownFromPeak < 0 ? "sell" : "default"}
      />
      <StatTile label="保有ポジション数" value={account.open_position_count} />
    </div>
  );
}
