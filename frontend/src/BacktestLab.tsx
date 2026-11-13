import { useEffect, useMemo, useRef, useState } from "react";
import { Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { type BacktestRequest, type BacktestResult, type Dataset, getDataCatalog, listStrategies, runBacktest } from "./api";
import { Link } from "react-router-dom";
import { useChartColors } from "./theme";
import TradeChart from "./TradeChart";

const SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD"];
const TFS = ["M1", "M5", "M15", "H1", "H4", "D1"];
const PERIODS = [{ v: 0, l: "All downloaded history" }, { v: 1095, l: "Last 3 years" }, { v: 730, l: "Last 2 years" }, { v: 365, l: "Last year" }, { v: 180, l: "Last 6 months" }];
const money = (n: number) => `${n < 0 ? "-" : ""}$${Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
const day = (iso: string) => iso.slice(0, 10);

export default function BacktestLab() {
  const cc = useChartColors();
  const tip = { background: cc.tipBg, border: `1px solid ${cc.tipBorder}`, color: cc.tipText };
  const [strategies, setStrategies] = useState<{ id: string; name: string }[]>([]);
  const [form, setForm] = useState<BacktestRequest>({
    strategy: "EMA-2", symbol: "EURUSD", timeframe: "M15", source: "store",
    days: 0, risk_pct: 0.5, cost_stress: 1, commission_per_lot: 0, include_holdout: false,
  });
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [compare, setCompare] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sort, setSort] = useState<{ key: "entry_ts" | "pnl"; dir: 1 | -1 }>({ key: "entry_ts", dir: 1 });
  const [selected, setSelected] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const chartRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!loading) return;
    const t0 = Date.now();
    const id = setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 500);
    return () => clearInterval(id);
  }, [loading]);

  const [datasets, setDatasets] = useState<Dataset[]>([]);
  useEffect(() => {
    listStrategies().then(setStrategies).catch((e) => setError(e.message));
    getDataCatalog().then((c) => setDatasets(c.datasets)).catch(() => {});
  }, []);

  const set = <K extends keyof BacktestRequest>(k: K, v: BacktestRequest[K]) => setForm((f) => ({ ...f, [k]: v }));

  async function run() {
    setLoading(true); setError(""); setElapsed(0);
    try {
      const r = await runBacktest(form);
      setCompare(result); // previous run becomes the comparison baseline
      setResult(r);
      setSelected(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  const trades = useMemo(() => {
    const t = [...(result?.trades ?? [])];
    t.sort((a, b) => (a[sort.key] > b[sort.key] ? 1 : -1) * sort.dir);
    return t;
  }, [result, sort]);

  const m = result?.metrics;
  const ds = datasets.find((d) => d.symbol === form.symbol && d.timeframe === form.timeframe);
  const pick = (i: number) => { setSelected(i); chartRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }); };
  const runBars = ds ? Math.round(ds.bars * (form.days ? Math.min(1, form.days / (ds.years * 365)) : 1) * (form.include_holdout ? 1 : 0.88)) : 0;
  return (
    <div className="lab">
      <section className="panel form">
        <h2>Run a backtest</h2>
        <label>Strategy
          <select value={form.strategy} onChange={(e) => set("strategy", e.target.value)}>
            {strategies.map((s) => <option key={s.id} value={s.id}>{s.id} · {s.name}</option>)}
          </select>
        </label>
        <label>Symbol
          <select value={form.symbol} onChange={(e) => set("symbol", e.target.value)}>
            {SYMBOLS.map((s) => <option key={s}>{s}</option>)}
          </select>
        </label>
        <label>Timeframe
          <select value={form.timeframe} onChange={(e) => set("timeframe", e.target.value)}>
            {TFS.map((s) => <option key={s}>{s}</option>)}
          </select>
        </label>
        <label>History
          <select value={form.days} onChange={(e) => set("days", +e.target.value)}>
            {PERIODS.map((p) => <option key={p.v} value={p.v}>{p.l}</option>)}
          </select>
          {ds ? <small>{ds.years} years of real {ds.symbol} {ds.timeframe} from Deriv · {day(ds.start)} → {day(ds.end)}</small>
            : <small className="err">Not downloaded yet. <Link to="/data">Download it on Market Data</Link>.</small>}
        </label>
        <label className="check">
          <input type="checkbox" checked={form.include_holdout} onChange={(e) => set("include_holdout", e.target.checked)} />
          <span>Include hold-out period{ds ? ` (from ${day(ds.holdout_start)})` : ""}</span>
        </label>
        <small className="hint">The last 6 months are kept aside as untouched test data. Leave this off while tuning a strategy.</small>
        <label>Risk per trade %
          <input type="number" step={0.05} min={0.05} max={5} value={form.risk_pct} onChange={(e) => set("risk_pct", +e.target.value)} />
        </label>
        <label>Commission / lot / side ($)
          <input type="number" step={0.5} min={0} value={form.commission_per_lot} onChange={(e) => set("commission_per_lot", +e.target.value)} />
        </label>
        <label>Cost stress ×{form.cost_stress.toFixed(2)}
          <input type="range" min={1} max={3} step={0.25} value={form.cost_stress} onChange={(e) => set("cost_stress", +e.target.value)} />
          <small>1.5× = the Gate 1 stress test (+50% spread and slippage)</small>
        </label>
        <button className="run" disabled={loading || !ds} onClick={run}>{loading ? "Running…" : "Run backtest"}</button>
        {error && <p className="err" role="alert">{error}</p>}
      </section>

      <section className="results">
        {loading && <RunProgress elapsed={elapsed} form={form} bars={runBars} />}
        {!result && !loading && <HowItWorks form={form} bars={runBars} />}
        {result && m && (
          <>
            {result.warning && <div className="warn">⚠ {result.warning}</div>}
            <div className="meta">
              {result.strategy} · {result.symbol} {result.timeframe} · {result.bars.toLocaleString()} bars ·
              {" "}{day(result.range[0])} → {day(result.range[1])} · data <code>{result.data_version}</code>
              {result.holdout_start && <> · {result.includes_holdout ? "includes" : "excludes"} hold-out from {day(result.holdout_start)}</>}
              <br />Costs: spread {result.costs.spread} · swap {money(result.costs.swap_long_per_lot)} long / {money(result.costs.swap_short_per_lot)} short per lot per night
              {result.costs.swap_from_broker ? " (Deriv rates)" : " (default)"} · commission {money(result.costs.commission_per_lot)}/lot · stress ×{result.costs.stress}
            </div>
            <div className="cards">
              <Card label="Net profit" value={money(m.net_profit)} tone={m.net_profit >= 0 ? "pos" : "neg"} sub={`${m.return_pct}%`} />
              <Card label="Profit factor" value={m.profit_factor?.toFixed(2) ?? "—"} tone={(m.profit_factor ?? 0) >= 1.3 ? "pos" : "neg"} sub="Gate 1 ≥ 1.3" />
              <Card label="Win rate" value={`${(m.win_rate * 100).toFixed(1)}%`} sub={`${m.trades} trades`} />
              <Card label="Max drawdown" value={`${m.max_drawdown_pct}%`} tone={m.max_drawdown_pct >= -15 ? "pos" : "neg"} sub="Gate 1 ≤ 15%" />
              <Card label="Sharpe" value={m.sharpe.toFixed(2)} sub={`Sortino ${m.sortino.toFixed(2)}`} />
              <Card label="Expectancy" value={money(m.expectancy)} sub={`fees ${money(m.total_fees)}`} />
            </div>
            {m.trades < 100 && <div className="warn">Only {m.trades} trades: Gate 1 needs ≥ 100 in the sample.</div>}

            <div ref={chartRef}>
              <TradeChart symbol={result.symbol} timeframe={result.timeframe} end={result.range[1]} trades={result.trades}
                selected={selected} onSelect={setSelected} />
            </div>

            <div className="panel">
              <h3>Equity {compare && <small className="muted">(dashed = previous run: {compare.strategy})</small>}</h3>
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={result.equity.map((p, i) => ({ ...p, prev: compare?.equity[i]?.equity }))}>
                  <CartesianGrid stroke={cc.grid} />
                  <XAxis dataKey="t" tickFormatter={day} minTickGap={50} stroke={cc.axis} />
                  <YAxis domain={["auto", "auto"]} stroke={cc.axis} width={60} />
                  <Tooltip contentStyle={tip} labelFormatter={(l) => String(l).slice(0, 16)} />
                  <Line dataKey="equity" stroke={cc.line} dot={false} strokeWidth={2} isAnimationActive={false} />
                  {compare && <Line dataKey="prev" stroke={cc.axis} dot={false} strokeDasharray="4 4" isAnimationActive={false} />}
                </LineChart>
              </ResponsiveContainer>
              <h3>Drawdown %</h3>
              <ResponsiveContainer width="100%" height={140}>
                <AreaChart data={result.equity}>
                  <CartesianGrid stroke={cc.grid} />
                  <XAxis dataKey="t" tickFormatter={day} minTickGap={50} stroke={cc.axis} />
                  <YAxis stroke={cc.axis} width={60} />
                  <Tooltip contentStyle={tip} labelFormatter={(l) => String(l).slice(0, 16)} />
                  <Area dataKey="dd" stroke={cc.down} fill={cc.down + "33"} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            <div className="panel">
              <h3>Trades ({trades.length}) <small className="muted">· click a row to see it on the chart</small> <small className="muted">exits: {Object.entries(m.exit_reasons).map(([k, v]) => `${k} ${v}`).join(" · ")}</small></h3>
              <div className="tablewrap">
                <table>
                  <thead><tr>
                    <th onClick={() => setSort({ key: "entry_ts", dir: sort.key === "entry_ts" ? (-sort.dir as 1 | -1) : 1 })}>Entry</th>
                    <th>Exit</th><th>Side</th><th>Lots</th><th>In</th><th>Out</th><th>Reason</th>
                    <th onClick={() => setSort({ key: "pnl", dir: sort.key === "pnl" ? (-sort.dir as 1 | -1) : -1 })}>PnL ▾</th>
                  </tr></thead>
                  <tbody>
                    {trades.slice(0, 200).map((t) => {
                      const idx = result.trades.indexOf(t);
                      return (
                      <tr key={idx} className={`trow ${idx === selected ? "selrow" : ""}`} onClick={() => pick(idx)}
                        tabIndex={0} onKeyDown={(e) => e.key === "Enter" && pick(idx)}>
                        <td>{t.entry_ts.slice(0, 16).replace("T", " ")}</td>
                        <td>{t.exit_ts.slice(0, 16).replace("T", " ")}</td>
                        <td className={t.side}>{t.side}</td><td>{t.qty}</td><td>{t.entry_px}</td><td>{t.exit_px}</td>
                        <td>{t.exit_reason}</td>
                        <td className={t.pnl >= 0 ? "pos" : "neg"}>{money(t.pnl)}</td>
                      </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {trades.length > 200 && <p className="muted">Showing first 200 of {trades.length}.</p>}
            </div>
          </>
        )}
      </section>
    </div>
  );
}

function Card({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "pos" | "neg" }) {
  return (
    <div className="card">
      <div className="muted">{label}</div>
      <div className={`big ${tone ?? ""}`}>{value}</div>
      {sub && <div className="muted small">{sub}</div>}
    </div>
  );
}

const STEPS = [
  { at: 0, title: "Load candles", text: "Read the downloaded Deriv history from Market Data (hold-out excluded unless ticked)." },
  { at: 2, title: "Prepare the strategy", text: "Compute indicators (EMAs, ATR, ADX) and candle patterns on closed candles only." },
  { at: 5, title: "Replay every candle", text: "Walk forward one closed candle at a time: the strategy may signal, the order fills at the next candle's open with half the spread + slippage, stop-loss / take-profit are checked on each candle, and swap is charged at each rollover." },
  { at: 99999, title: "Score the run", text: "Equity curve, drawdown, profit factor, win rate, Sharpe and costs; then the chart marks every trade." },
];

function HowItWorks({ form, bars }: { form: BacktestRequest; bars: number }) {
  return (
    <div className="panel howto">
      <h3>What happens when you press “Run backtest”</h3>
      <p className="muted">{form.strategy} is replayed on real {form.symbol} {form.timeframe} candles{bars ? ` (about ${bars.toLocaleString()} bars)` : ""}, as if it had traded at the time, with Deriv's spreads and swap. Nothing is sent to MT5: no real or demo orders are placed.</p>
      <ol>{STEPS.map((s) => <li key={s.title}><b>{s.title}.</b> {s.text}</li>)}</ol>
      <p className="muted">You then get the results cards, a <b>price chart</b> with every trade's entry ▲▼ and exit ● marked (click a trade to zoom in and see its entry, stop-loss and take-profit), the equity and drawdown curves, and the trade list. Years of M15 data take about 1–2 minutes.</p>
    </div>
  );
}

function RunProgress({ elapsed, form, bars }: { elapsed: number; form: BacktestRequest; bars: number }) {
  const current = STEPS.filter((s) => elapsed >= s.at).length - 1;
  return (
    <div className="panel howto" role="status" aria-live="polite">
      <h3>Running {form.strategy} on {form.symbol} {form.timeframe}… <small className="muted">{elapsed}s</small></h3>
      <ol className="steps">{STEPS.map((s, i) => (
        <li key={s.title} className={i < current ? "done" : i === current ? "now" : ""}><b>{s.title}.</b> {s.text}</li>))}
      </ol>
      <div className="meter"><i style={{ width: `${Math.min(95, (elapsed / Math.max(20, bars / 900)) * 100)}%` }} /></div>
      <small className="muted">Progress is estimated from the number of candles; long M15/M5 runs take 1–2 minutes.</small>
    </div>
  );
}
