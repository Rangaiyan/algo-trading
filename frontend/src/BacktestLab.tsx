import { useEffect, useMemo, useState } from "react";
import { Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { type BacktestRequest, type BacktestResult, listStrategies, runBacktest } from "./api";
import { useChartColors } from "./theme";

const SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD"];
const TFS = ["M5", "M15", "M30", "H1", "H4"];
const money = (n: number) => `${n < 0 ? "-" : ""}$${Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
const day = (iso: string) => iso.slice(0, 10);

export default function BacktestLab() {
  const cc = useChartColors();
  const tip = { background: cc.tipBg, border: `1px solid ${cc.tipBorder}`, color: cc.tipText };
  const [strategies, setStrategies] = useState<{ id: string; name: string }[]>([]);
  const [form, setForm] = useState<BacktestRequest>({
    strategy: "EMA-2", symbol: "EURUSD", timeframe: "M15", source: "synthetic",
    days: 150, risk_pct: 0.5, cost_stress: 1, commission_per_lot: 0,
  });
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [compare, setCompare] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sort, setSort] = useState<{ key: "entry_ts" | "pnl"; dir: 1 | -1 }>({ key: "entry_ts", dir: 1 });

  useEffect(() => {
    listStrategies().then(setStrategies).catch((e) => setError(e.message));
  }, []);

  const set = <K extends keyof BacktestRequest>(k: K, v: BacktestRequest[K]) => setForm((f) => ({ ...f, [k]: v }));

  async function run() {
    setLoading(true); setError("");
    try {
      const r = await runBacktest(form);
      setCompare(result); // previous run becomes the comparison baseline
      setResult(r);
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
        <label>Data source
          <select value={form.source} onChange={(e) => set("source", e.target.value as "synthetic" | "store")}>
            <option value="synthetic">Synthetic (test only)</option>
            <option value="store">Stored real data</option>
          </select>
        </label>
        {form.source === "synthetic" && (
          <label>Days of data
            <input type="number" min={10} max={2000} value={form.days} onChange={(e) => set("days", +e.target.value)} />
          </label>
        )}
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
        <button className="run" disabled={loading} onClick={run}>{loading ? "Running…" : "Run backtest"}</button>
        {error && <p className="err" role="alert">{error}</p>}
      </section>

      <section className="results">
        {!result && !loading && <p className="muted">Configure a run and press “Run backtest”. Results appear here.</p>}
        {result && m && (
          <>
            {result.warning && <div className="warn">⚠ {result.warning}</div>}
            <div className="meta">
              {result.strategy} · {result.symbol} {result.timeframe} · {result.bars.toLocaleString()} bars ·
              {" "}{day(result.range[0])} → {day(result.range[1])} · data <code>{result.data_version}</code>
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
              <h3>Trades ({trades.length}) <small className="muted">exits: {Object.entries(m.exit_reasons).map(([k, v]) => `${k} ${v}`).join(" · ")}</small></h3>
              <div className="tablewrap">
                <table>
                  <thead><tr>
                    <th onClick={() => setSort({ key: "entry_ts", dir: sort.key === "entry_ts" ? (-sort.dir as 1 | -1) : 1 })}>Entry</th>
                    <th>Exit</th><th>Side</th><th>Lots</th><th>In</th><th>Out</th><th>Reason</th>
                    <th onClick={() => setSort({ key: "pnl", dir: sort.key === "pnl" ? (-sort.dir as 1 | -1) : -1 })}>PnL ▾</th>
                  </tr></thead>
                  <tbody>
                    {trades.slice(0, 200).map((t, i) => (
                      <tr key={i}>
                        <td>{t.entry_ts.slice(0, 16).replace("T", " ")}</td>
                        <td>{t.exit_ts.slice(0, 16).replace("T", " ")}</td>
                        <td className={t.side}>{t.side}</td><td>{t.qty}</td><td>{t.entry_px}</td><td>{t.exit_px}</td>
                        <td>{t.exit_reason}</td>
                        <td className={t.pnl >= 0 ? "pos" : "neg"}>{money(t.pnl)}</td>
                      </tr>
                    ))}
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
