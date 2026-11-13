import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Play, Save, Square } from "lucide-react";
import { type OptJob, type OptRequest, cancelJob, getJob, listStrategies, saveToLibrary, startOptimize } from "../api";
import { GateTable, MetricRows, Params, Verdict } from "./common";
import { money, pctv, pf, tone } from "./format";

const SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD"];
const TFS = ["M15", "H1", "H4"];
const JOB_KEY = "rinz.optJob";

/** Optimiser (Phase 3): tune on training data only, then validate with walk-forward, Monte Carlo, sensitivity,
 *  cost stress and cross-pair, and score against Gate 1. */
export default function Optimizer() {
  const nav = useNavigate();
  const loc = useLocation() as { state?: { strategy?: string; base?: Record<string, unknown>; symbol?: string; timeframe?: string } };
  const [strategies, setStrategies] = useState<{ id: string; name: string }[]>([]);
  const [req, setReq] = useState<OptRequest>({
    strategy: loc.state?.strategy ?? "EMA-2", symbol: loc.state?.symbol ?? "EURUSD", timeframe: loc.state?.timeframe ?? "H1",
    trials: 60, walk_forward: true, wf_train_months: 12, wf_test_months: 3, wf_trials: 15, base: loc.state?.base ?? {},
  });
  const [jobId, setJobId] = useState<string | null>(() => { try { return localStorage.getItem(JOB_KEY); } catch { return null; } });
  const [job, setJob] = useState<OptJob | null>(null);
  const [err, setErr] = useState("");
  const [name, setName] = useState("");
  const [saved, setSaved] = useState("");

  useEffect(() => { listStrategies().then(setStrategies).catch((e) => setErr(e.message)); }, []);

  useEffect(() => {
    if (!jobId) return;
    let dead = false;
    const tick = async () => {
      try {
        const j = await getJob(jobId);
        if (!dead && j.kind && j.kind !== "optimize") { setJobId(null); return; }
        if (!dead) setJob(j);
        if (j.status === "running" && !dead) setTimeout(tick, 1500);
      } catch (e) { if (!dead) { setErr((e as Error).message); setJobId(null); } }
    };
    tick();
    return () => { dead = true; };
  }, [jobId]);

  async function start() {
    setErr(""); setSaved("");
    try {
      const { job_id } = await startOptimize(req);
      try { localStorage.setItem(JOB_KEY, job_id); } catch { /* ignore */ }
      setJob(null); setJobId(job_id);
    } catch (e) { setErr((e as Error).message); }
  }

  async function save() {
    if (!job) return;
    try {
      const e = await saveToLibrary({ job_id: job.id, name });
      setSaved(e.id);
    } catch (e) { setErr((e as Error).message); }
  }

  const set = <K extends keyof OptRequest>(k: K, v: OptRequest[K]) => setReq((r) => ({ ...r, [k]: v }));
  const running = job?.status === "running";
  const r = job?.result;
  const isRule = req.strategy === "RULE";

  return (
    <>
      <section className="desk-head" style={{ ["--dc" as string]: "#22c55e" }}>
        <div className="lbl" style={{ color: "#22c55e" }}>BUILDER + OPTIMISER</div>
        <h2>Optimiser &amp; validation</h2>
        <p className="muted">Searches settings on the <b>training</b> data only (first 75% before the hold-out), then checks the winner the way the plan's Gate 1 requires:
          validation period, walk-forward, Monte Carlo, neighbouring settings, +50% costs and the other pairs. The last 6 months stay untouched for the one-time hold-out test in the Strategy Library.</p>
      </section>

      <div className="opt-grid">
        <section className="panel form">
          <h3>Run</h3>
          <label>Strategy
            <select value={req.strategy} onChange={(e) => set("strategy", e.target.value)} disabled={running}>
              {strategies.filter((s) => s.id !== "RULE" || isRule).map((s) => <option key={s.id} value={s.id}>{s.id} · {s.name}</option>)}
            </select>
            {isRule && <small>Rule from the Rule Builder: the optimiser tunes its threshold, exits and structure settings.</small>}
          </label>
          <div className="small muted">Pair(s) <span title="Two or more pairs = a basket: one rule set with the same settings on every pair, tuned and judged on the combined result">ⓘ</span></div>
          <div className="multi" style={{ marginBottom: 6 }}>{SYMBOLS.map((sym) => {
            const sel = req.symbols?.length ? req.symbols : [req.symbol];
            const on = sel.includes(sym);
            return <button key={sym} type="button" className={`chip x ${on ? "on" : ""}`} disabled={running} aria-pressed={on}
              onClick={() => {
                const next = on ? sel.filter((x) => x !== sym) : [...sel, sym];
                if (next.length) setReq((r) => ({ ...r, symbol: next[0], symbols: next.length > 1 ? next : undefined }));
              }}>{sym}</button>;
          })}</div>
          <small className="hint">{req.symbols && req.symbols.length > 1
            ? `Basket of ${req.symbols.length}: settings are shared and tuned on the combined training data; Gate 1 judges the combined trades and checks no single pair carries it.`
            : "Pick two or more pairs to test the rules as a basket."}</small>
          <label>Timeframe<select value={req.timeframe} onChange={(e) => set("timeframe", e.target.value)} disabled={running}>{TFS.map((s) => <option key={s}>{s}</option>)}</select>
            <small>H1 is quickest. M15 takes several minutes.</small></label>
          <label>Settings to try
            <input type="number" min={0} max={500} value={req.trials} onChange={(e) => set("trials", +e.target.value)} disabled={running} />
            <small>{req.trials === 0 ? "0 = validate the current settings as they are" : "More tries find better-looking training results, but also more luck."}</small>
          </label>
          <label className="check"><input type="checkbox" checked={req.walk_forward} onChange={(e) => set("walk_forward", e.target.checked)} disabled={running} /> <span>Walk-forward</span></label>
          {req.walk_forward && (
            <div className="row3">
              <label>Train months<input type="number" min={3} max={36} value={req.wf_train_months} onChange={(e) => set("wf_train_months", +e.target.value)} disabled={running} /></label>
              <label>Test months<input type="number" min={1} max={12} value={req.wf_test_months} onChange={(e) => set("wf_test_months", +e.target.value)} disabled={running} /></label>
              <label>Tries / window<input type="number" min={0} max={100} value={req.wf_trials} onChange={(e) => set("wf_trials", +e.target.value)} disabled={running} /></label>
            </div>
          )}
          {running
            ? <button className="run danger" onClick={() => job && cancelJob(job.id)}><Square size={14} /> Cancel</button>
            : <button className="run" onClick={start}><Play size={14} /> Optimise &amp; validate</button>}
          {err && <p className="err" role="alert">{err}</p>}
        </section>

        <section>
          {!job && !jobId && (
            <div className="panel howto">
              <h3>What this does</h3>
              <ol>
                <li><b>Search</b> (Optuna) on the training period, scored on Sharpe, profit factor and drawdown with at least 30 trades, never on raw profit.</li>
                <li><b>Validation period:</b> the winner on the next 25%, which it never saw.</li>
                <li><b>Walk-forward:</b> re-tune on each year and trade the following 3 months; efficiency = out-of-sample ÷ in-sample return.</li>
                <li><b>Monte Carlo:</b> 2,000 reshuffles of the trades with random extra costs: worst-case drawdown and chance of profit.</li>
                <li><b>Sensitivity:</b> every setting nudged one step up and down; real edges survive small changes.</li>
                <li><b>Cost stress</b> (+50% spread and slippage) and <b>cross-pair</b> (same settings on the other 4 pairs).</li>
                <li><b>Gate 1 checklist.</b> Save the result to the Strategy Library, then run the hold-out test there, once.</li>
              </ol>
              <p className="muted">If nothing passes, the right answer is “keep researching”, not “lower the bar” (plan §10.6).</p>
            </div>
          )}

          {job && (job.status === "running" || job.status === "error") && (
            <div className="panel howto" role="status" aria-live="polite">
              <h3>{job.status === "error" ? "Failed" : `${job.request.strategy} on ${job.request.symbols?.length ? job.request.symbols.join("+") : job.request.symbol} ${job.request.timeframe}: ${job.stage}…`}</h3>
              {job.status === "running" && <div className="meter"><i style={{ width: `${Math.min(99, (job.done / Math.max(1, job.total)) * 100)}%` }} /></div>}
              <small className="muted">{job.done} / {job.total} steps</small>
              {job.error && <p className="err">{job.error}</p>}
              <pre className="data-log">{job.log.slice(-8).join("\n")}</pre>
            </div>
          )}

          {r && (
            <>
              <div className="panel opt-head">
                <div>
                  <Verdict v={r.verdict} />
                  <h3 style={{ margin: "8px 0 4px" }}>{r.strategy} · {r.symbol} {r.timeframe}</h3>
                  <div className="muted small">Train {r.split.train.join(" → ")} · validation {r.split.validation.join(" → ")} · hold-out {r.split.holdout.join(" → ")} (untouched)</div>
                  <div style={{ marginTop: 8 }}>Chosen settings: <Params p={r.tuned} /></div>
                </div>
                <div className="opt-save">
                  <input placeholder="Name (optional)" value={name} onChange={(e) => setName(e.target.value)} aria-label="Library name" />
                  <button className="run" onClick={save} disabled={!!saved}><Save size={14} /> {saved ? "Saved" : "Save to library"}</button>
                  {saved && <button className="link" onClick={() => nav("/library")}>Open Strategy Library →</button>}
                </div>
              </div>

              <div className="panel"><h3>Gate 1</h3><GateTable rows={r.gate1} /></div>

              <div className="panel">
                <h3>Results by period</h3>
                <MetricRows rows={[
                  { label: "Defaults", m: r.defaults_insample, note: "(before tuning, in-sample)" },
                  { label: "Training", m: r.train, note: "(what was optimised)" },
                  { label: "Validation", m: r.validation, note: "(unseen)" },
                  { label: "In-sample total", m: r.insample },
                  { label: "Costs +50%", m: r.cost_stress },
                ]} />
                <p className="muted small" style={{ marginTop: 8 }}>{r.multiple_testing_note}</p>
              </div>

              {r.walk_forward && (
                <div className="panel">
                  <h3>Walk-forward <small className="muted">efficiency {Math.round(r.walk_forward.efficiency * 100)}% · {r.walk_forward.oos_profitable_windows}/{r.walk_forward.windows.length} test windows profitable · {r.walk_forward.oos_trades} out-of-sample trades</small></h3>
                  <div className="wf-bars" aria-label="Out-of-sample return per window">
                    {r.walk_forward.windows.map((w, i) => {
                      const v = w.out.return_pct, h = Math.min(100, Math.abs(v) * 8);
                      return <div key={i} title={`${w.test.join(" → ")}: ${pctv(v)} (${w.out.trades} trades, PF ${pf(w.out.profit_factor)})`}>
                        <span className="wf-up">{v > 0 && <i style={{ height: `${h}%`, background: "var(--green)" }} />}</span>
                        <span className="wf-dn">{v < 0 && <i style={{ height: `${h}%`, background: "var(--red)" }} />}</span>
                        <small>{w.test[0].slice(2, 7)}</small>
                      </div>;
                    })}
                  </div>
                  <small className="muted">Annualised: in-sample {pctv(r.walk_forward.annual_in_pct)} vs out-of-sample {pctv(r.walk_forward.annual_out_pct)}</small>
                </div>
              )}

              <div className="two">
                <div className="panel">
                  <h3>Monte Carlo</h3>
                  {r.monte_carlo.runs ? (
                    <dl className="kv">
                      <dt>Chance of profit</dt><dd>{Math.round((r.monte_carlo.profit_probability ?? 0) * 100)}%</dd>
                      <dt>Return (5% / median / 95%)</dt><dd>{pctv(r.monte_carlo.return_pct!.p5)} / {pctv(r.monte_carlo.return_pct!.p50)} / {pctv(r.monte_carlo.return_pct!.p95)}</dd>
                      <dt>Max drawdown (median / worst 5%)</dt><dd>{r.monte_carlo.max_dd_pct!.p50}% / {r.monte_carlo.max_dd_pct!.p95}%</dd>
                      <dt>Runs</dt><dd>{r.monte_carlo.runs.toLocaleString()} × {r.monte_carlo.trades} trades</dd>
                    </dl>
                  ) : <p className="muted">{r.monte_carlo.note}</p>}
                </div>
                <div className="panel">
                  <h3>Other pairs <small className="muted">same settings</small></h3>
                  <table className="tbl"><thead><tr><th>Pair</th><th>Trades</th><th>Net</th><th>PF</th></tr></thead>
                    <tbody>{r.cross_pair.map((p) => <tr key={p.symbol}><td>{p.symbol}{p.is_target && " ★"}</td><td>{p.trades}</td>
                      <td className={tone(p.net_profit)}>{money(p.net_profit)}</td><td>{pf(p.profit_factor)}</td></tr>)}</tbody></table>
                </div>
              </div>

              <div className="panel">
                <h3>Sensitivity <small className="muted">{r.sensitivity.profitable_share == null ? "" : `${Math.round(r.sensitivity.profitable_share * 100)}% of neighbouring settings profitable`}</small></h3>
                <div className="tablewrap"><table className="tbl"><thead><tr><th>Change</th><th>Trades</th><th>Net</th><th>PF</th><th>Max DD</th></tr></thead>
                  <tbody>{r.sensitivity.neighbours.map((n) => <tr key={n.change}><td>{n.change}</td><td>{n.trades}</td>
                    <td className={tone(n.net_profit)}>{money(n.net_profit)}</td><td>{pf(n.profit_factor)}</td><td>{n.max_drawdown_pct.toFixed(1)}%</td></tr>)}</tbody></table></div>
              </div>
            </>
          )}
        </section>
      </div>
    </>
  );
}
