export type Direction = "BUY" | "SELL";
export type Granularity = "M1" | "M5" | "M15" | "H1" | "H4" | "D";
export type SignalLabel = "強い買い" | "買い" | "様子見" | "売り" | "強い売り";
export type ReasonStatus = "met" | "partial" | "failed";
export type TrendRegime = "UPTREND" | "DOWNTREND" | "RANGE" | "UNKNOWN";
export type VolatilityRegime = "HIGH_VOLATILITY" | "LOW_VOLATILITY" | "NORMAL";

export interface Instrument {
  symbol: string;
  display_name: string;
  pip_size: number;
  price_precision: number;
  is_watched: boolean;
}

export interface PriceSnapshot {
  instrument: string;
  bid: number;
  ask: number;
  mid: number;
  spread: number;
  day_high: number;
  day_low: number;
  change: number;
  change_pct: number;
  ts: string;
}

export interface Candle {
  instrument: string;
  granularity: Granularity;
  open_time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  is_final: boolean;
}

export interface SignalReason {
  status: ReasonStatus;
  text: string;
  points: number;
}

export interface SignalResponse {
  instrument: string;
  granularity: Granularity;
  direction: Direction;
  score: number;
  buy_score: number;
  sell_score: number;
  label: SignalLabel;
  regime: { trend: TrendRegime; volatility: VolatilityRegime };
  reasons: SignalReason[];
}

export interface BacktestSummaryMetrics {
  total_pnl: number;
  return_pct: number;
  trade_count: number;
  win_rate_pct: number;
  avg_win: number;
  avg_loss: number;
  profit_factor: number | null;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  max_consecutive_wins: number;
  max_consecutive_losses: number;
}

export interface BacktestSummary {
  overall: BacktestSummaryMetrics;
  in_sample: BacktestSummaryMetrics;
  out_of_sample: BacktestSummaryMetrics;
}

export interface BacktestResult {
  id: string;
  summary: BacktestSummary;
  equity_curve: { time: string; equity: number }[];
  trade_count: number;
}

export interface BacktestTrade {
  id: string;
  segment: "in_sample" | "out_of_sample";
  direction: Direction;
  entry_time: string;
  entry_price: number;
  exit_time: string | null;
  exit_price: number | null;
  size: number;
  stop_loss: number | null;
  take_profit: number | null;
  pnl: number;
  entry_reasons: SignalReason[];
  exit_reason: string;
}

export interface PaperAccount {
  balance: number;
  high_water_mark: number;
  currency: string;
  open_position_count: number;
}

export interface PaperPosition {
  id: string;
  instrument: string;
  direction: Direction;
  size: number;
  entry_price: number;
  stop_loss: number | null;
  take_profit: number | null;
  opened_at: string;
}

export interface TradeJournalEntry {
  id: string;
  source: "backtest" | "paper" | "demo" | "live";
  pair: string;
  direction: Direction;
  entry_time: string;
  entry_price: number;
  exit_time: string;
  exit_price: number;
  size: number;
  stop_loss: number | null;
  take_profit: number | null;
  pnl: number;
  reason: string;
  signal_score: number | null;
  strategy_code: string | null;
  market_regime: string | null;
  closed_at: string;
}

export interface WinRateBreakdown {
  dimension: string;
  breakdown: { key: string; trades: number; win_rate_pct: number; total_pnl: number }[];
}

export interface SystemStatus {
  broker_provider: string;
  market_data_provider: string;
  providers_split: boolean;
  broker_environment: string;
  broker_connected: boolean;
  kill_switch_active: boolean;
  auto_mode: "manual" | "semi_auto" | "full_auto";
  live_trading_enabled_env: boolean;
  live_trading_admin_enabled: boolean;
  app_env: string;
  watchlist: string[];
}

export interface RiskSettings {
  max_risk_per_trade_pct: number;
  max_daily_loss_pct: number;
  max_drawdown_pct: number;
  max_concurrent_positions: number;
  max_same_symbol_positions: number;
  consecutive_loss_stop_count: number;
  max_spread_pips_default: number;
  kill_switch_active: boolean;
  auto_mode: "manual" | "semi_auto" | "full_auto";
  live_trading_admin_enabled: boolean;
}

export interface SimulationState {
  id: string;
  instrument: string;
  direction: Direction;
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  size: number;
  status: "open" | "closed_tp" | "closed_sl" | "closed_manual";
  current_price: number;
  current_pnl: number;
  max_favorable: number;
  max_adverse: number;
  risk_reward_ratio: number;
  closed_price: number | null;
}

export interface ReplayDecisionRecord {
  decided_at_index: number;
  action: "BUY" | "SELL" | "SKIP";
  entry_price: number | null;
  exit_price: number | null;
  pnl: number | null;
  max_favorable: number;
  max_adverse: number;
  explanation: SignalReason[] | null;
}

export interface ReplaySessionState {
  id: string;
  instrument: string;
  granularity: Granularity;
  training_mode: boolean;
  current_index: number;
  total_candles: number;
  is_at_end: boolean;
  has_open_decision: boolean;
  candles: Candle[];
  decisions: ReplayDecisionRecord[];
  new_candle?: Candle | null;
}

export interface NotificationItem {
  id: string;
  ts: string;
  channel: string;
  kind: string;
  title: string;
  body: string;
  is_read: boolean;
}
