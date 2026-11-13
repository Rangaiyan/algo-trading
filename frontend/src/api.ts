// The backend runs on port 8000 of the same machine that serves this page (works on this PC and from a phone).
import { withToken } from "./auth";
export const API = import.meta.env.VITE_API_URL ?? `${window.location.protocol}//${window.location.hostname}:8000`;

export type Metrics = {
  trades: number; net_profit: number; return_pct: number; win_rate: number;
  avg_win: number; avg_loss: number; profit_factor: number | null; expectancy: number;
  max_drawdown_pct: number; sharpe: number; sortino: number; longest_losing_streak: number;
  total_fees: number; exit_reasons: Record<string, number>;
};
export type Trade = {
  entry_ts: string; exit_ts: string; side: "buy" | "sell"; qty: number;
  entry_px: number; exit_px: number; pnl: number; fees: number; exit_reason: string;
  stop_loss: number | null; take_profit: number | null; pips: number; r_multiple: number; bars_held: number;
  mfe_pips: number; mae_pips: number; session: string;
};

export type Candle = { time: number; open: number; high: number; low: number; close: number };
export async function getCandles(symbol: string, timeframe: string, opts: { start?: string; end?: string; limit?: number } = {}): Promise<Candle[]> {
  const q = new URLSearchParams({ symbol, timeframe });
  if (opts.start) q.set("start", opts.start);
  if (opts.end) q.set("end", opts.end);
  if (opts.limit) q.set("limit", String(opts.limit));
  const r = await fetch(`${API}/data/candles?${q}`);
  if (!r.ok) throw new Error(`Could not load candles (${r.status})`);
  return (await r.json()).candles;
}
export type BacktestResult = {
  strategy: string; symbol: string; timeframe: string; source: string; bars: number;
  data_version: string; range: [string, string]; metrics: Metrics;
  equity: { t: string; equity: number; dd: number }[]; trades: Trade[]; warning: string | null;
  holdout_start: string | null; includes_holdout: boolean;
  costs: { spread: string; swap_long_per_lot: number; swap_short_per_lot: number; swap_from_broker: boolean; commission_per_lot: number; stress: number };
};
export type BacktestRequest = {
  strategy: string; symbol: string; timeframe: string; source: "store";
  days: number; risk_pct: number; cost_stress: number; commission_per_lot: number; include_holdout: boolean;
  params?: Record<string, unknown>;
};

export type Dataset = {
  symbol: string; timeframe: string; source: string; bars: number; start: string; end: string; years: number;
  holdout_start: string; data_version: string; updated_at: string;
  quality: { ok: boolean; rows: number; duplicates: number; bad_ohlc: number; weekend_bars: number; gaps: number; issues: string[]; cleaned_rows: number };
};
export type DataCatalog = {
  datasets: Dataset[];
  job: { running: boolean; started_at: string | null; finished_at: string | null; error: string | null };
  log: string[];
};
export async function getDataCatalog(): Promise<DataCatalog> {
  const r = await fetch(`${API}/data/catalog`);
  if (!r.ok) throw new Error(`Could not load data catalog (${r.status})`);
  return r.json();
}
export async function startDownload(body: { symbols?: string[]; timeframes?: string[]; years?: number } = {}): Promise<void> {
  const r = await fetch(`${API}/data/download`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) {
    const b = await r.json().catch(() => ({}));
    throw new Error(typeof b.detail === "string" ? b.detail : `Download failed to start (${r.status})`);
  }
}

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

// ---------------- Phase 3: optimiser, library, rule builder ----------------
export type Slim = { trades: number; net_profit: number; return_pct: number; win_rate: number; profit_factor: number | null; max_drawdown_pct: number; sharpe: number; sortino: number; expectancy: number };
export type GateRow = { criterion: string; status: "pass" | "fail" | "pending"; value: unknown; required: string };
export type WFWindow = { train: string[]; test: string[]; params: Record<string, unknown>; in: Slim; out: Slim };
export type OptReport = {
  strategy: string; symbol: string; timeframe: string; params: Record<string, unknown>; tuned: Record<string, unknown>;
  split: { train: string[]; validation: string[]; holdout: string[] }; data_version: string; trials: number; best_score: number;
  history: ({ trial: number; score: number } & Slim)[]; train: Slim; validation: Slim; insample: Slim; defaults_insample: Slim;
  walk_forward: { windows: WFWindow[]; annual_in_pct: number; annual_out_pct: number; efficiency: number; oos_trades: number; oos_profitable_windows: number } | null;
  monte_carlo: { runs: number; trades?: number; profit_probability?: number; return_pct?: { p5: number; p50: number; p95: number }; max_dd_pct?: { p50: number; p95: number }; note?: string };
  sensitivity: { neighbours: ({ change: string } & Slim)[]; profitable_share: number | null; worst_pf: number | null };
  cost_stress: Slim; cross_pair: ({ symbol: string; is_target: boolean } & Slim)[];
  holdout: ({ period: string[]; run_at?: string; first_run?: boolean } & Slim) | null;
  gate1: GateRow[]; verdict: "pass" | "fail" | "pending"; multiple_testing_note: string;
};
export type OptRequest = { strategy: string; symbol: string; timeframe: string; trials: number; walk_forward: boolean; wf_train_months: number; wf_test_months: number; wf_trials: number; base?: Record<string, unknown> };
export type OptJob = { id: string; kind?: string; status: "running" | "done" | "error" | "cancelled"; request: OptRequest; stage: string; done: number; total: number; log: string[]; error: string | null; started_at: string; finished_at: string | null; result: OptReport | null };
export type LibEntry = {
  id: string; name: string; strategy: string; symbol: string; timeframe: string; status: string; created_at: string; updated_at: string;
  holdout_used: boolean; params: Record<string, unknown>; verdict: string | null; insample: Slim | null; validation: Slim | null; gate1: GateRow[] | null; holdout: OptReport["holdout"];
};
export type LibFull = LibEntry & { report: OptReport | null; history: { status: string; at: string; note: string }[]; versions: { v: number; params: Record<string, unknown>; at: string }[]; spec: unknown };

async function jx<T>(r: Response): Promise<T> {
  if (!r.ok) {
    const b = await r.json().catch(() => ({}));
    throw new Error(typeof b.detail === "string" ? b.detail : `Request failed (${r.status})`);
  }
  return r.json();
}
const post = (url: string, body?: unknown) => fetch(`${API}${url}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });

export const startOptimize = (req: OptRequest) => post("/optimize", req).then((r) => jx<{ job_id: string }>(r));
export const getJob = (id: string) => fetch(`${API}/optimize/${id}`).then((r) => jx<OptJob>(r));
export const cancelJob = (id: string) => post(`/optimize/${id}/cancel`).then((r) => jx<unknown>(r));
export const listLibrary = () => fetch(`${API}/library`).then((r) => jx<LibEntry[]>(r));
export const getLibrary = (id: string) => fetch(`${API}/library/${id}`).then((r) => jx<LibFull>(r));
export const saveToLibrary = (body: { job_id?: string; name?: string; strategy?: string; symbol?: string; timeframe?: string; params?: Record<string, unknown> }) =>
  post("/library", body).then((r) => jx<LibFull>(r));
export const promoteEntry = (id: string, to: string, note = "") => post(`/library/${id}/promote`, { to, note }).then((r) => jx<LibFull>(r));
export const runHoldout = (id: string, confirmRerun = false) => post(`/library/${id}/holdout${confirmRerun ? "?confirm_rerun=true" : ""}`).then((r) => jx<LibFull>(r));
export const deleteEntry = (id: string) => fetch(`${API}/library/${id}`, { method: "DELETE" }).then((r) => jx<unknown>(r));
export type BuilderInfo = { blocks: Record<string, string>; sessions: Record<string, [string, string]>; levels: string[]; patterns: string[]; example: RuleSpec };
export type RuleBlock = { block: string; weight?: number; [k: string]: unknown };
export type RuleSpec = {
  name?: string; mode?: "all" | "score"; threshold?: number; structure?: { swing_n?: number; displacement_k?: number; fvg_min_atr?: number };
  filters?: { sessions?: string[]; max_spread_pips?: number }; setup: RuleBlock[];
  entry?: { type?: "zone" | "market"; zone?: string[]; at?: "edge" | "mid"; expires_bars?: number };
  exit?: { stop?: "sweep" | "zone" | "atr"; buffer_atr?: number; atr_mult?: number; take_profit?: { type?: "rr" | "next_liquidity"; rr?: number; min_rr?: number } };
};
export const builderInfo = () => fetch(`${API}/builder/blocks`).then((r) => jx<BuilderInfo>(r));
export const validateSpec = (spec: unknown) => post("/builder/validate", { spec }).then((r) => jx<{ errors: string[] }>(r));

// ---------------- Phase 4: strategy generator ----------------
export type GenCandidate = { describe: string; score: number; train: Slim; spec: RuleSpec };
export type GenResult = {
  symbol: string; timeframe: string; method: string; population: number; generations: number; evaluated: number;
  train_period: string[]; luck_sharpe: number; curve: { generation: number; best: number; median?: number; evaluated: number }[];
  leaderboard: GenCandidate[]; survivors: { describe: string; score: number; spec: RuleSpec; report: OptReport }[]; passed: number;
};
export type GenRequest = { symbol: string; timeframe: string; method: "genetic" | "random"; population: number; generations: number; survivors: number; seed: number };
export type GenJob = Omit<OptJob, "result" | "request"> & { kind: string; request: GenRequest; result: GenResult | null };
export const startGenerate = (req: GenRequest) => post("/generate", req).then((r) => jx<{ job_id: string }>(r));
export const getGenJob = (id: string) => fetch(`${API}/optimize/${id}`).then((r) => jx<GenJob>(r));
export const saveCandidate = (job_id: string, candidate: number, name = "") => post("/library", { job_id, candidate, name }).then((r) => jx<LibFull>(r));

// ---------------- Phase 5: trading engine, risk, investment, reports ----------------
export type TradeSession = {
  id: string; name: string; strategy: string; symbol: string; timeframe: string; params: Record<string, unknown>; mode: "paper" | "shakedown";
  library_id: string | null; magic: number; status: "running" | "paused" | "stopped"; created_at: string; started_at?: string;
  last_bar: string | null; last_signal: { bar: string; side: string; entry: number | null; sl: number; tp: number | null; reason: string; decision?: string } | null;
  last_error: string | null;
};
export type OrderRec = {
  tag: string; session_id: string; session_name: string; strategy: string; symbol: string; side: string; type: string; lots: number;
  requested_price: number; stop_loss: number; take_profit: number | null; state: string; placed_at: string; mode: string;
  fill_price?: number; slippage_pips?: number; spread_pips?: number; latency_ms?: number; retcode?: number; reason?: string;
  exit_price?: number; pnl?: number; exit_reason?: string; closed_at?: string; risk_money?: number;
};
export type RiskConfig = {
  risk_pct: number; max_risk_pct: number; max_open_positions: number; max_per_symbol: number; max_usd_exposure: number;
  daily_loss_limit_pct: number; weekly_loss_limit_pct: number; max_drawdown_pct: number; min_margin_level_pct: number;
  max_trades_per_day: number; max_spread_pips: Record<string, number>;
};
export type TradingStatus = {
  state: { last_tick: string | null; last_error: string | null; connected: boolean | null; issues: { key: string; msg: string; at: string }[] };
  risk: { config: RiskConfig; state: { halt: string | null; halt_reason: string; halted_at: string | null; events: { at: string; kind: string; msg: string }[] };
          usage: { day_pct?: number; week_pct?: number; drawdown_pct?: number; limits?: { day: number; week: number; drawdown: number } } };
  sessions: TradeSession[]; orders: OrderRec[]; loop_seconds: number; account: LiveAccount;
  execution: { orders: number; filled: number; rejected: number; avg_slippage_pips: number | null; avg_spread_pips: number | null; avg_latency_ms: number | null; rejection_rate: number | null };
};
export const tradingStatus = () => fetch(`${API}/trading/status`).then((r) => jx<TradingStatus>(r));
export const addTradeSession = (body: { library_id?: string; strategy?: string; symbol?: string; timeframe?: string; params?: Record<string, unknown>; name?: string; acknowledge_unvalidated?: boolean }) =>
  post("/trading/sessions", body).then((r) => jx<TradeSession>(r));
export const setSessionStatus = (id: string, status: string) => post(`/trading/sessions/${id}/status`, { status }).then((r) => jx<TradeSession>(r));
export const deleteSession = (id: string) => fetch(`${API}/trading/sessions/${id}`, { method: "DELETE" }).then((r) => jx<unknown>(r));
export const tickNow = () => post("/trading/tick").then((r) => jx<{ alerts: string[] }>(r));
export const updateRisk = (patch: Partial<RiskConfig>) => fetch(`${API}/risk/config`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) }).then((r) => jx<RiskConfig>(r));
export const killSwitch = (include_manual = false) => post("/risk/kill", { confirm: "FLATTEN", include_manual }).then((r) => jx<{ closed: unknown[]; cancelled: unknown[]; failed: { reason: string }[] }>(r));
export const resumeTrading = () => post("/risk/resume").then((r) => jx<{ halted: boolean; note: string }>(r));
export type Investment = {
  currency: string; server: string; mode: string; invested: number; deposits: number; withdrawals: number; current_value: number; net_profit: number;
  return_pct: number | null; today_pnl: number; twr_pct: number | null; xirr_pct: number | null; max_drawdown_pct: number; best_day_pct: number | null; worst_day_pct: number | null;
  costs: { commission: number; swap: number; fees: number }; curve: { t: string; balance: number; index: number; cash: number }[];
  monthly_pct: { month: string; pct: number }[]; by_strategy: { strategy: string; trades: number; pnl: number }[]; by_symbol: { symbol: string; pnl: number }[];
  ledger: { ts: string; type: string; amount: number; comment: string }[]; as_of: string;
};
export const getInvestment = () => fetch(`${API}/investment/summary`).then((r) => jx<Investment>(r));
export type ReportSummary = { period: string; from: string | null; to: string; account: string; mode: string; currency: string; equity: number; trades: number; net_pnl: number;
  wins: number; losses: number; win_rate: number | null; profit_factor: number | null; best: number | null; worst: number | null;
  by_strategy: { strategy: string; trades: number; pnl: number; wins: number }[]; by_symbol: { symbol: string; trades: number; pnl: number }[]; text: string; disclaimer: string };
export const reportSummary = (period: string) => fetch(`${API}/reports/summary?period=${period}`).then((r) => jx<ReportSummary>(r));
export const reportUrl = (kind: "trades.csv" | "performance.html", period: string) => withToken(`${API}/reports/${kind}?period=${period}`);

// ---------------- Gate 0: engine vs MT5 Strategy Tester ----------------
export type Gate0Info = { path: string; exists: boolean; modified?: string; trades?: number | null; tolerances: Record<string, number>; ea_source: string };
export type Gate0Result = {
  symbol: string; timeframe: string; params: Record<string, number>; lots: number; period: string[]; verdict: "pass" | "fail";
  checks: { check: string; value: string; required: string; ok: boolean }[];
  summary: { ea_trades: number; our_trades: number; matched: number; match_rate: number; ea_net: number; our_net: number; ea_pf: number | null; our_pf: number | null;
    exit_reason_agreement: number; median_entry_diff_pips: number | null; median_exit_diff_pips: number | null; same_bar_exit_share: number | null };
  unmatched_mt5: { side: string; open_time: string; open_price: number }[]; unmatched_rinz: { side: string; open_time: string; open_price: number }[];
  largest_differences: { side: string; open_time: string; entry_diff_pips: number; exit_diff_pips: number; ea_reason: string; our_reason: string; ea_pnl: number; our_pnl: number }[];
  notes: string[]; costs: Record<string, unknown>;
};
export const gate0Info = () => fetch(`${API}/gate0/info`).then((r) => jx<Gate0Info>(r));
export const gate0Compare = (csv?: string) => post("/gate0/compare", csv ? { csv } : {}).then((r) => jx<Gate0Result>(r));

// ---------------- Backtest stage: campaign ----------------
export type Baseline = { strategy: string; symbol: string; timeframe: string; score?: number; error?: string } & Partial<Slim>;
export type CampaignCandidate = {
  source: "optimiser" | "generator"; strategy: string; symbol: string; timeframe: string; describe?: string; verdict: "pass" | "fail" | "pending";
  params: Record<string, unknown>; gate1: GateRow[]; train: Slim; validation: Slim; insample: Slim; walk_forward_efficiency: number | null;
  cross_pair: { symbol: string; profit_factor: number | null }[]; library_id?: string; baseline?: { trades: number; profit_factor: number | null; return_pct: number; score: number };
};
export type Campaign = {
  id: string; started_at: string; finished_at: string; settings: { symbols: string[]; timeframes: string[]; strategies: string[]; shortlist: number; trials: number; wf_trials: number; generator: boolean };
  gate0: { status: string; at?: string; match_rate?: number; note?: string }; baselines: Baseline[]; shortlist: Baseline[]; candidates: CampaignCandidate[];
  passed: number; saved_to_library: string[]; cancelled: boolean; conclusion: string;
};
export type CampaignReq = { symbols?: string[]; timeframes: string[]; strategies?: string[]; shortlist: number; trials: number; wf_trials: number; generator: boolean; save_passing: boolean };
export const startCampaign = (req: CampaignReq) => post("/campaign", req).then((r) => jx<{ job_id: string }>(r));
export const listCampaigns = () => fetch(`${API}/campaigns`).then((r) => jx<{ campaigns: (Omit<Campaign, "baselines" | "shortlist" | "candidates" | "conclusion"> & { candidates: number; baselines: number })[]; gate0: Campaign["gate0"] }>(r));
export const getCampaign = (id: string) => fetch(`${API}/campaigns/${id}`).then((r) => jx<Campaign>(r));
export const getAnyJob = (id: string) => fetch(`${API}/optimize/${id}`).then((r) => jx<{ id: string; kind: string; status: string; stage: string; done: number; total: number; log: string[]; error: string | null; result: unknown }>(r));

// ---------------- Gate 2 (paper trading) + news ----------------
export type Gate2Session = {
  session: { id: string; name: string; strategy: string; symbol: string; timeframe: string; mode: string; status: string; library_id: string | null };
  since: string; weeks: number; verdict: "pass" | "fail" | "pending";
  paper: { trades: number; net: number; win_rate: number | null; profit_factor: number | null; avg_r: number | null; avg_hold_hours: number | null; max_dd_money: number };
  expected: { profit_factor: number | null; win_rate: number | null; trades: number | null; trades_per_week: number | null; mc_p95_dd_pct: number | null } | null;
  execution: { avg_slippage_pips: number | null; avg_spread_pips: number | null; rejected: number }; criteria: GateRow[];
};
export type Gate2 = { sessions: Gate2Session[]; drills: { key: string; drill: string; done: boolean; note?: string; at?: string }[]; criteria: Record<string, number>; as_of: string };
export const getGate2 = () => fetch(`${API}/gate2`).then((r) => jx<Gate2>(r));
export const markDrill = (key: string, done: boolean, note = "") => post(`/gate2/drills/${key}`, { done, note }).then((r) => jx<unknown>(r));
export type NewsEvent = { title: string; currency: string; impact: string; at: string; forecast?: string; previous?: string };
export const getNews = () => fetch(`${API}/news`).then((r) => jx<{ filter_on: boolean; before_min: number; after_min: number; impacts: string[]; fetched_at: string | null; error: string | null; events: NewsEvent[] }>(r));
