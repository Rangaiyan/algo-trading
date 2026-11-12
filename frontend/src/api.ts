export const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export type Metrics = {
  trades: number; net_profit: number; return_pct: number; win_rate: number;
  avg_win: number; avg_loss: number; profit_factor: number | null; expectancy: number;
  max_drawdown_pct: number; sharpe: number; sortino: number; longest_losing_streak: number;
  total_fees: number; exit_reasons: Record<string, number>;
};
export type Trade = {
  entry_ts: string; exit_ts: string; side: "buy" | "sell"; qty: number;
  entry_px: number; exit_px: number; pnl: number; fees: number; exit_reason: string;
};
export type BacktestResult = {
  strategy: string; symbol: string; timeframe: string; source: string; bars: number;
  data_version: string; range: [string, string]; metrics: Metrics;
  equity: { t: string; equity: number; dd: number }[]; trades: Trade[]; warning: string | null;
};
export type BacktestRequest = {
  strategy: string; symbol: string; timeframe: string; source: "synthetic" | "store";
  days: number; risk_pct: number; cost_stress: number; commission_per_lot: number;
};

export async function runBacktest(req: BacktestRequest): Promise<BacktestResult> {
  const r = await fetch(`${API}/backtests`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(req),
  });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (${r.status})`);
  }
  return r.json();
}

export async function listStrategies(): Promise<{ id: string; name: string }[]> {
  const r = await fetch(`${API}/backtests/strategies`);
  if (!r.ok) throw new Error("Could not load strategies");
  return r.json();
}

export type Agg = { pnl: number; trades: number; win_rate: number; pips: number; long_pnl: number; short_pnl: number };
export type Dash = {
  empty: boolean; source: string; warning: string; built_at: string; as_of: string; initial_capital: number; sessions: number;
  filters: { desk: string | null; symbol: string | null }; available: { desks: string[]; symbols: string[] };
  account: null | { equity: number; balance: number; margin_used: number; free_margin: number; margin_level: number; leverage: number };
  career: Agg & { since: string; trading_days: number; avg_day: number; booked: number; floating: number; open_positions: number };
  today: Agg & { date: string; high: number; high_ts: string | null; low: number; kept_pct: number | null };
  week: Agg & { vs_last: number; days: { day: string; pnl: number | null }[] };
  month: Agg & { vs_last: number };
  kpis: {
    win_rate: number; wins: number; losses: number; streak: number; best_win_run: number; worst_loss_run: number; avg_day: number;
    max_loss: { pnl: number; symbol: string; date: string }; best_day: { pnl: number; date: string }; worst_day: { pnl: number; date: string };
    deepest_dip: number; long_pnl: number; short_pnl: number; high_water: { pnl: number; date: string }; lowest: { pnl: number; date: string };
    profit_factor: number | null; expectancy: number; avg_win: number; avg_loss: number; costs: number; cost_per_trade: number;
    cost_breakdown: { spread_cost: number; slippage_cost: number; commission: number; swap: number };
    gross_before_costs: number; avg_mfe_pips: number; avg_mae_pips: number; avg_r: number;
  };
  days_last_30: { date: string; pnl: number; trades: number }[];
  weeks_last_12: (Agg & { start: string })[]; months_last_4: (Agg & { month: string })[];
  equity: { date: string; pnl: number; cum: number; equity: number; trades: number }[];
  by_symbol: Record<string, Agg>; by_desk: Record<string, Agg>;
};

export async function getDashboard(desk: string, symbol: string, rebuild = false): Promise<Dash> {
  const q = new URLSearchParams();
  if (desk) q.set("desk", desk);
  if (symbol) q.set("symbol", symbol);
  if (rebuild) q.set("rebuild", "true");
  const r = await fetch(`${API}/ledger/dashboard?${q}`);
  if (!r.ok) throw new Error(`Dashboard request failed (${r.status})`);
  return r.json();
}

// ---------------- desk pages ----------------
export type DayBlock = { date: string; pnl: number; wins: number; losses: number } | null;
export type SessionMetrics = {
  trades: number; net: number; booked: number; open: number; open_legs: number; peak: number; low: number; wins: number; losses: number;
  win_pct: number; per_trade: number; pips: number; today: DayBlock; prev_day: DayBlock; since: string | null;
};
export type Session = {
  id: string; name: string; desk: string; strategy: string; symbol: string; timeframe: string; mode: string; status: "running" | "paused" | "stopped" | "archived";
  initial_balance: number; started_at: string; risk_pct: number; sides: string; settings: Record<string, string | number>; metrics: SessionMetrics;
};
export type TradeRow = {
  id: number; session_id: string; desk: string; strategy: string; symbol: string; side: "buy" | "sell"; qty: number;
  entry_ts: string; exit_ts: string; entry_px: number; exit_px: number; stop_loss: number; take_profit: number | null;
  pnl: number; pips: number; gross_pnl: number; fees: number; commission: number; swap: number; spread_cost: number; slippage_cost: number;
  mfe_pips: number; mae_pips: number; mfe_money: number; mae_money: number; risk_money: number; r_multiple: number; bars_held: number;
  entry_session: string; exit_reason: string; peak_profit: number; given_back: number; kept_pct: number; held_minutes: number; overnight: boolean;
  best_price: number; worst_price: number; pip_size: number; stop_pips: number | null; target_pips: number | null; planned_rr: number | null; capture: number | null; total_costs: number;
};
export type Marker = { time: number; kind: "entry" | "exit"; side: "buy" | "sell"; price: number; trade_id: number; pnl: number; reason?: string };
export type ChartData = {
  symbol: string; timeframe: string; last_price: number; bar_seconds: number; markers: Marker[];
  candles: { time: number; open: number; high: number; low: number; close: number }[];
};

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) {
    const b = await r.json().catch(() => ({}));
    throw new Error(typeof b.detail === "string" ? b.detail : `Request failed (${r.status})`);
  }
  return r.json();
}
export const listSessions = (desk: string, includeArchived = false) =>
  fetch(`${API}/ledger/sessions?${new URLSearchParams({ ...(desk ? { desk } : {}), ...(includeArchived ? { include_archived: "true" } : {}) })}`)
    .then((r) => j<{ source: string; warning: string; as_of: string | null; sessions: Session[] }>(r));
export const sessionAction = (id: string, action: string) =>
  fetch(`${API}/ledger/sessions/${id}/${action}`, { method: "POST" }).then((r) => j<{ id: string; status: Session["status"] }>(r));
export const getChart = (id: string, around?: number, bars = 400) =>
  fetch(`${API}/ledger/sessions/${id}/chart?${new URLSearchParams({ bars: String(bars), ...(around ? { around: String(around) } : {}) })}`).then((r) => j<ChartData>(r));
export const getTrades = (p: Record<string, string | number | undefined>) =>
  fetch(`${API}/ledger/trades?${new URLSearchParams(Object.entries(p).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)]))}`)
    .then((r) => j<{ total: number; net: number; wins: number; trades: TradeRow[] }>(r));
export const getTrade = (id: number) =>
  fetch(`${API}/ledger/trades/${id}`).then((r) => j<{ trade: TradeRow; session: { id: string; name: string; desk: string } }>(r));
