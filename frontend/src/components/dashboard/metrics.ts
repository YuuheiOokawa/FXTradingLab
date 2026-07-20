import type { PaperAccount, TradeJournalEntry } from "@/types/api";

export interface JournalStats {
  totalPnl: number;
  todayPnl: number;
  todayTradeCount: number;
  winRatePct: number | null;
  profitFactor: number | null;
  maxDrawdown: number;
  maxDrawdownPct: number | null;
}

function isSameLocalDay(iso: string, ref: Date): boolean {
  const d = new Date(iso);
  return (
    d.getFullYear() === ref.getFullYear() &&
    d.getMonth() === ref.getMonth() &&
    d.getDate() === ref.getDate()
  );
}

/**
 * Derives dashboard-level P/L, win-rate, profit-factor, and max-drawdown stats
 * from the raw journal trade list (there is no dedicated summary endpoint yet).
 * Max drawdown is computed by replaying trades in chronological order over an
 * equity curve anchored at the current paper balance minus total realized pnl.
 */
export function computeJournalStats(trades: TradeJournalEntry[], account?: PaperAccount): JournalStats {
  const now = new Date();
  const totalPnl = trades.reduce((sum, t) => sum + t.pnl, 0);
  const todayTrades = trades.filter((t) => isSameLocalDay(t.closed_at, now));
  const todayPnl = todayTrades.reduce((sum, t) => sum + t.pnl, 0);

  const wins = trades.filter((t) => t.pnl > 0).length;
  const winRatePct = trades.length > 0 ? (wins / trades.length) * 100 : null;

  const grossWin = trades.filter((t) => t.pnl > 0).reduce((s, t) => s + t.pnl, 0);
  const grossLoss = trades.filter((t) => t.pnl < 0).reduce((s, t) => s + t.pnl, 0);
  const profitFactor = grossLoss < 0 ? grossWin / Math.abs(grossLoss) : grossWin > 0 ? Infinity : null;

  const sorted = [...trades].sort((a, b) => new Date(a.closed_at).getTime() - new Date(b.closed_at).getTime());
  const startEquity = account ? account.balance - totalPnl : 0;
  let equity = startEquity;
  let peak = startEquity;
  let maxDrawdown = 0;
  let maxDrawdownPct = 0;
  for (const t of sorted) {
    equity += t.pnl;
    if (equity > peak) peak = equity;
    const dd = peak - equity;
    if (dd > maxDrawdown) {
      maxDrawdown = dd;
      maxDrawdownPct = peak !== 0 ? (dd / peak) * 100 : 0;
    }
  }

  return {
    totalPnl,
    todayPnl,
    todayTradeCount: todayTrades.length,
    winRatePct,
    profitFactor,
    maxDrawdown,
    maxDrawdownPct: trades.length > 0 ? maxDrawdownPct : null,
  };
}
