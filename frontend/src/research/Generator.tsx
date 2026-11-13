import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown, ChevronRight, Dna, Save, Square } from "lucide-react";
import { type GenJob, type GenRequest, cancelJob, getGenJob, saveCandidate, startGenerate } from "../api";
import { GateTable, MetricRows, Verdict } from "./common";
import { pf, pctv } from "./format";

const SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD"];
const TFS = ["M15", "H1", "H4"];
const JOB_KEY = "rinz.genJob";

/** Strategy Generator (Phase 4, doc 9.3): genetic / random search over rule blocks, survivors fully validated. */
export default function Generator() {
  const nav = useNavigate();
  const [req, setReq] = useState<GenRequest>({ symbol: "EURUSD", timeframe: "H1", method: "genetic", population: 24, generations: 6, survivors: 3, seed: 7 });
  const [jobId, setJobId] = useState<string | null>(() => { try { return localStorage.getItem(JOB_KEY); } catch { return null; } });
  const [job, setJob] = useState<GenJob | null>(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState<number | null>(0);
  const [saved, setSaved] = useState<Record<number, string>>({});

  useEffect(() => {
    if (!jobId) return;
    let dead = false;
    const tick = async () => {
      try {
        const j = await getGenJob(jobId);
        if (dead) return;
        if (j.kind !== "generate") { setJobId(null); return; }
        setJob(j);
        if (j.status === "running") setTimeout(tick, 1500);
      } catch { if (!dead) setJobId(null); }
    };
    tick();
    return () => { dead = true; };
  }, [jobId]);

  async function start() {
    setErr(""); setSaved({});
    try {
      const { job_id } = await startGenerate(req);
      try { localStorage.setItem(JOB_KEY, job_id); } catch { /* ignore */ }
      setJob(null); setJobId(job_id);
    } catch (e) { setErr((e as Error).message); }
  }

  const set = <K extends keyof GenRequest>(k: K, v: GenRequest[K]) => setReq((r) => ({ ...r, [k]: v }));
  const running = job?.status === "running";
  const r = job?.result;
  const evals = req.population * req.generations;

  return (
    <>
      <section className="desk-head" style={{ ["--dc" as string]: "#2dd4bf" }}>
        <div className="lbl" style={{ color: "#2dd4bf" }}>STRATEGY GENERATOR</div>
        <h2>Strategy Generator</h2>
        <p className="muted">Rinz builds its own candidates by combining the Rule Builder's blocks (sweeps, BOS/CHoCH, H4 bias, premium/discount, EMA, candles, sessions,
          zones, stops, targets). It scores them on <b>training data only</b>, then puts the best few <i>different</i> designs through the full Gate 1 validation.
          The plan is blunt about it: auto-generation easily creates curve-fit strategies, and the validation is the part that matters.</p>
      </section>

      <div className="opt-grid">
        <section className="panel form">
          <h3>Search</h3>
          <label>Pair<select value={req.symbol} onChange={(e) => set("symbol", e.target.value)} disabled={running}>{SYMBOLS.map((s) => <option key={s}>{s}</option>)}</select></label>
          <label>Timeframe<select value={req.timeframe} onChange={(e) => set("timeframe", e.target.value)} disabled={running}>{TFS.map((s) => <option key={s}>{s}</option>)}</select>
            <small>H1 is quickest. M15 is about 4× slower.</small></label>
          <label>Method<select value={req.method} onChange={(e) => set("method", e.target.value as "genetic" | "random")} disabled={running}>
            <option value="genetic">Genetic (breed and mutate the best)</option><option value="random">Random search (baseline)</option></select></label>
          <div className="row3">
            <label>Population<input type="number" min={4} max={200} value={req.population} onChange={(e) => set("population", +e.target.value)} disabled={running} /></label>
            <label>Generations<input type="number" min={1} max={50} value={req.generations} onChange={(e) => set("generations", +e.target.value)} disabled={running} /></label>
            <label>Survivors<input type="number" min={1} max={10} value={req.survivors} onChange={(e) => set("survivors", +e.target.value)} disabled={running} /></label>
          </div>
          <label>Random seed<input type="number" value={req.seed} onChange={(e) => set("seed", +e.target.value)} disabled={running} />
            <small>Same seed and settings give the same run. Up to {evals} candidates, then {req.survivors} validations.</small></label>
          {running
            ? <button className="run danger" onClick={() => job && cancelJob(job.id)}><Square size={14} /> Cancel</button>
            : <button className="run" onClick={start}><Dna size={14} /> Generate &amp; validate</button>}
          {err && <p className="err" role="alert">{err}</p>}
        </section>

        <section>
          {!job && (
            <div className="panel howto">
              <h3>How it works</h3>
              <ol>
                <li><b>Random designs:</b> each candidate is a full rule (trigger, 1–4 extra blocks, all-must-pass or confluence score, entry, stop, target, structure settings).</li>
                <li><b>Score on training data</b> with the optimiser's score: Sharpe, profit factor and drawdown, at least 30 trades.</li>
                <li><b>Breed:</b> keep the 2 best, pick parents by tournament, mix their blocks and settings, mutate (toggle a block, change a weight, swap the stop…).</li>
                <li><b>Survivors:</b> the best designs that differ in shape (blocks, entry, stop and target type) go through validation, walk-forward, Monte Carlo, sensitivity, cost stress, cross-pair and Gate 1.</li>
                <li><b>Luck check:</b> with N candidates tried, the best one looks good by chance. Survivors must beat that luck benchmark too.</li>
              </ol>
            </div>
          )}

          {job && job.status !== "done" && (
            <div className="panel howto" role="status" aria-live="polite">
              <h3>{job.status === "error" ? "Failed" : job.status === "cancelled" ? "Cancelled" : `${job.request.method} search on ${job.request.symbol} ${job.request.timeframe}: ${job.stage}…`}</h3>
              {running && <div className="meter"><i style={{ width: `${Math.min(99, (job.done / Math.max(1, job.total)) * 100)}%` }} /></div>}
              <small className="muted">{job.done} / {job.total} steps</small>
              {job.error && <p className="err">{job.error}</p>}
              <pre className="data-log">{job.log.slice(-10).join("\n")}</pre>
            </div>
          )}

          {r && (
            <>
              <div className="panel opt-head">
                <div>
                  <span className={`verdict ${r.passed ? "pending" : "fail"}`}>{r.passed ? `${r.passed} SURVIVOR(S) STILL IN THE RUNNING` : "NO SURVIVOR PASSES GATE 1"}</span>
                  <h3 style={{ margin: "8px 0 4px" }}>{r.evaluated} candidates · {r.symbol} {r.timeframe} · {r.method}</h3>
                  <div className="muted small">Training period {r.train_period.join(" → ")}. By luck alone, the best of {r.evaluated} skill-less strategies would show a training Sharpe of about <b>{r.luck_sharpe}</b>.</div>
                </div>
                <div className="gen-curve" aria-label="Best training score per generation">
                  {r.curve.map((c) => {
                    const lo = Math.min(...r.curve.map((x) => x.best), 0), hi = Math.max(...r.curve.map((x) => x.best), 0.01);
                    return <div key={c.generation} title={`generation ${c.generation}: best ${c.best}`}><i style={{ height: `${Math.max(4, ((c.best - lo) / (hi - lo)) * 100)}%` }} /><small>{c.generation}</small></div>;
                  })}
                </div>
              </div>

              <h3 className="sec">Survivors (validated)</h3>
              {r.survivors.length === 0 && <div className="panel"><p className="muted">No candidate had enough training trades in a distinct shape. Try a larger population, more generations or another timeframe.</p></div>}
              <div className="lib-list">
                {r.survivors.map((s, i) => (
                  <article key={i} className={`panel lib-item ${open === i ? "open" : ""}`}>
                    <button className="lib-row" onClick={() => setOpen(open === i ? null : i)} aria-expanded={open === i}>
                      {open === i ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                      <span className="lib-name"><b>#{i + 1}</b><small className="muted">{s.describe}</small></span>
                      <Verdict v={s.report.verdict} />
                      <span className="lib-num"><small className="muted">train PF</small><b>{pf(s.report.train.profit_factor)}</b></span>
                      <span className="lib-num"><small className="muted">validation PF</small><b>{pf(s.report.validation.profit_factor)}</b></span>
                      <span className="lib-num"><small className="muted">walk-fwd</small><b>{s.report.walk_forward ? `${Math.round(s.report.walk_forward.efficiency * 100)}%` : "—"}</b></span>
                    </button>
                    {open === i && (
                      <div className="lib-body">
                        <div className="lib-actions">
                          <button className="pill on" disabled={!!saved[i]} onClick={() => job && saveCandidate(job.id, i).then((e) => setSaved((x) => ({ ...x, [i]: e.id }))).catch((e) => setErr(e.message))}>
                            <Save size={13} /> {saved[i] ? "Saved to library" : "Save to library"}</button>
                          <button className="pill" onClick={() => nav("/builder", { state: { spec: s.spec, symbol: r.symbol, timeframe: r.timeframe } })}>Open in Rule Builder</button>
                          {saved[i] && <button className="link" onClick={() => nav("/library")}>Strategy Library →</button>}
                        </div>
                        <GateTable rows={s.report.gate1} />
                        <div style={{ marginTop: 12 }}>
                          <MetricRows rows={[{ label: "Training", m: s.report.train }, { label: "Validation", m: s.report.validation },
                            { label: "In-sample", m: s.report.insample }, { label: "Costs +50%", m: s.report.cost_stress }]} />
                        </div>
                      </div>
                    )}
                  </article>
                ))}
              </div>

              <h3 className="sec">Leaderboard (training scores only, not validated)</h3>
              <div className="panel"><div className="tablewrap"><table className="tbl lead">
                <thead><tr><th>#</th><th>Design</th><th>Score</th><th>Trades</th><th>PF</th><th>Return</th><th>Sharpe</th><th></th></tr></thead>
                <tbody>{r.leaderboard.map((c, i) => (
                  <tr key={i}><td>{i + 1}</td><td className="lead-d">{c.describe}</td><td>{c.score.toFixed(2)}</td><td>{c.train.trades}</td>
                    <td>{pf(c.train.profit_factor)}</td><td className={c.train.return_pct >= 0 ? "up" : "down"}>{pctv(c.train.return_pct)}</td><td>{c.train.sharpe.toFixed(2)}</td>
                    <td><button className="link" onClick={() => nav("/builder", { state: { spec: c.spec, symbol: r.symbol, timeframe: r.timeframe } })}>open</button></td></tr>))}
                </tbody></table></div></div>
            </>
          )}
        </section>
      </div>
    </>
  );
}
