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

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) {
    const b = await r.json().catch(() => ({}));
    throw new Error(typeof b.detail === "string" ? b.detail : `Request failed (${r.status})`);
  }
  return r.json();
}

export type LivePosition = { id: string; symbol: string; side: "buy" | "sell"; qty: number; entry_price: number; stop_loss: number | null; take_profit: number | null; unrealized_pnl: number; opened_at: string; magic?: number; strategy?: string };
export type ClosedTrade = { position_id: number; symbol: string; side: "buy" | "sell"; volume: number; entry_price: number; exit_price: number; opened_at: string; closed_at: string; pnl: number; magic?: number; strategy?: string };
export type LiveAccount =
  | { connected: false; detail: string }
  | {
      connected: true; server: string; mode: string; currency: string; balance: number; equity: number; floating: number;
      margin_used: number; free_margin: number; margin_level: number | null; leverage: number; positions: LivePosition[];
      history_available: boolean; deposits?: number; pnl?: { today: number; week: number; month: number; all: number };
      total_pnl?: number; return_pct?: number | null; trades?: number; wins?: number; losses?: number; win_rate?: number | null; recent?: ClosedTrade[];
      balance_curve?: { t: string; balance: number }[];
    };
export const getLiveAccount = () => fetch(`${API}/account/live`).then((r) => j<LiveAccount>(r));

export type DeskStrategy = { strategy: string; magic: number; trades: number; net: number; wins: number; win_rate: number | null };
export type DeskData =
  | { connected: false; detail: string }
  | {
      connected: true; desk: string; currency: string; history_available: boolean; magic_range: [number, number];
      net: number; floating: number; trades: number; wins: number; losses: number; win_rate: number | null;
      avg_win: number | null; avg_loss: number | null; profit_factor: number | null; best: number | null; worst: number | null;
      strategies: DeskStrategy[]; positions: LivePosition[]; closed: ClosedTrade[]; curve: { t: string; cum: number }[];
    };
export const getDeskTrades = (desk: string) => fetch(`${API}/account/desk/${desk}`).then((r) => j<DeskData>(r));
