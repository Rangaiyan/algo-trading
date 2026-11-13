import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown, ChevronRight, Play, Square } from "lucide-react";
import { type Campaign as Camp, type CampaignReq, cancelJob, getAnyJob, getCampaign, listCampaigns, listStrategies, startCampaign } from "../api";
import { GateTable, Params, Verdict } from "./common";
import { pf } from "./format";

const SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD"];
const TFS = ["M15", "H1", "H4"];
const JOB_KEY = "rinz.campaignJob";

function heat(p: number | null | undefined) {
  if (p == null) return "var(--panel2)";
  const x = Math.max(-1, Math.min(1, (p - 1) / 0.5));
  return x >= 0 ? `color-mix(in srgb, var(--green) ${Math.round(x * 55)}%, var(--panel2))` : `color-mix(in srgb, var(--red) ${Math.round(-x * 55)}%, var(--panel2))`;
}

/** Backtest stage (plan §10.3): baselines -> shortlist -> optimise + validate -> ranked report, as one job. */
export default function Campaign() {
  const nav = useNavigate();
  const [strategies, setStrategies] = useState<string[]>([]);
  const [req, setReq] = useState<CampaignReq>({ symbols: SYMBOLS, timeframes: ["H1", "H4"], shortlist: 6, trials: 40, wf_trials: 10, generator: false, save_passing: true });
  const [jobId, setJobId] = useState<string | null>(() => { try { return localStorage.getItem(JOB_KEY); } catch { return null; } });
  const [job, setJob] = useState<{ status: string; stage: string; done: number; total: number; log: string[]; error: string | null } | null>(null);
  const [list, setList] = useState<Awaited<ReturnType<typeof listCampaigns>> | null>(null);
  const [camp, setCamp] = useState<Camp | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [err, setErr] = useState("");

  const loadList = useCallback(() => listCampaigns().then((l) => { setList(l); return l; }).catch((e) => { setErr(e.message); return null; }), []);
  useEffect(() => {
    listStrategies().then((s) => setStrategies(s.map((x) => x.id).filter((x) => x !== "RULE"))).catch(() => {});
    loadList().then((l) => { if (l?.campaigns[0]) getCampaign(l.campaigns[0].id).then(setCamp).catch(() => {}); });
  }, [loadList]);

  useEffect(() => {
    if (!jobId) return;
    let dead = false;
    const tick = async () => {
      try {
        const j = await getAnyJob(jobId);
        if (dead) return;
        if (j.kind !== "campaign") { setJobId(null); return; }
        setJob(j);
        if (j.status === "running") setTimeout(tick, 2000);
        else if (j.result) { setCamp(j.result as Camp); loadList(); }
      } catch { if (!dead) setJobId(null); }
    };
    tick();
    return () => { dead = true; };
  }, [jobId, loadList]);

  async function start() {
    setErr("");
    try {
      const { job_id } = await startCampaign({ ...req, strategies: req.strategies?.length ? req.strategies : undefined });
      try { localStorage.setItem(JOB_KEY, job_id); } catch { /* ignore */ }
      setJob(null); setJobId(job_id);
    } catch (e) { setErr((e as Error).message); }
  }

  const running = job?.status === "running";
  const toggle = (k: "symbols" | "timeframes", v: string) => setReq((r) => {
    const cur = r[k] ?? [];
    return { ...r, [k]: cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v] };
  });
  const grid = useMemo(() => {
    if (!camp) return null;
    const strats = [...new Set(camp.baselines.map((b) => b.strategy))];
    const cols = camp.settings.symbols.flatMap((s) => camp.settings.timeframes.map((t) => `${s} ${t}`));
    const at = (st: string, col: string) => camp.baselines.find((b) => b.strategy === st && `${b.symbol} ${b.timeframe}` === col);
    return { strats, cols, at };
  }, [camp]);
  const g0 = camp?.gate0 ?? list?.gate0;

  return (
    <>
      <section className="desk-head" style={{ ["--dc" as string]: "#a855f7" }}>
        <div className="lbl" style={{ color: "#a855f7" }}>BACKTEST STAGE · PLAN §10.3</div>
        <h2>Backtest Campaign</h2>
        <p className="muted">The plan's one-month backtest stage as one job: every strategy's default settings on every pair (in-sample), the strongest distinct combinations
          optimised on training data and validated against Gate 1, ranked in one report. Candidates that pass everything except the hold-out are saved to the Strategy Library,
          where the hold-out is run once.</p>
        {g0 && <p className={`small ${g0.status === "pass" ? "up" : "amb"}`}>Gate 0: <b>{g0.status}</b>{g0.status !== "pass" && " — results only count once the engine has been verified against the MT5 Strategy Tester (Gate 0 Check page)."}</p>}
      </section>

      <div className="opt-grid">
        <section className="panel form">
          <h3>New campaign</h3>
          <div className="small muted">Pairs</div>
          <div className="multi" style={{ marginBottom: 10 }}>{SYMBOLS.map((s) => <button key={s} type="button" className={`chip x ${req.symbols?.includes(s) ? "on" : ""}`} onClick={() => toggle("symbols", s)} disabled={running}>{s}</button>)}</div>
          <div className="small muted">Timeframes</div>
          <div className="multi" style={{ marginBottom: 10 }}>{TFS.map((s) => <button key={s} type="button" className={`chip x ${req.timeframes.includes(s) ? "on" : ""}`} onClick={() => toggle("timeframes", s)} disabled={running}>{s}</button>)}</div>
          <div className="small muted">Strategies (none selected = all {strategies.length})</div>
          <div className="multi" style={{ marginBottom: 10 }}>{strategies.map((s) => <button key={s} type="button" className={`chip x ${req.strategies?.includes(s) ? "on" : ""}`}
            onClick={() => setReq((r) => ({ ...r, strategies: r.strategies?.includes(s) ? r.strategies.filter((x) => x !== s) : [...(r.strategies ?? []), s] }))} disabled={running}>{s}</button>)}</div>
          <div className="row3">
            <label>Shortlist<input type="number" min={1} max={20} value={req.shortlist} onChange={(e) => setReq({ ...req, shortlist: +e.target.value })} disabled={running} /></label>
            <label>Tries each<input type="number" min={0} max={300} value={req.trials} onChange={(e) => setReq({ ...req, trials: +e.target.value })} disabled={running} /></label>
            <label>Walk-fwd tries<input type="number" min={0} max={60} value={req.wf_trials} onChange={(e) => setReq({ ...req, wf_trials: +e.target.value })} disabled={running} /></label>
          </div>
          <label className="check"><input type="checkbox" checked={req.generator} onChange={(e) => setReq({ ...req, generator: e.target.checked })} disabled={running} /> <span>Also run the strategy generator per pair/timeframe</span></label>
          <label className="check"><input type="checkbox" checked={req.save_passing} onChange={(e) => setReq({ ...req, save_passing: e.target.checked })} disabled={running} /> <span>Save candidates that pass Gate 1 to the library</span></label>
          <small className="hint">H1 + H4 on 5 pairs with a shortlist of 6 takes about 15 minutes; M15 and the generator add more. Nothing is traded.</small>
          {running ? <button className="run danger" onClick={() => jobId && cancelJob(jobId)}><Square size={14} /> Cancel</button>
            : <button className="run" onClick={start} disabled={!req.symbols?.length || !req.timeframes.length}><Play size={14} /> Run campaign</button>}
          {err && <p className="err" role="alert">{err}</p>}
          {list && list.campaigns.length > 0 && (<>
            <h4 className="lib-h">Past campaigns</h4>
            <ul className="camp-list">{list.campaigns.map((c) => <li key={c.id}><button className="link" onClick={() => getCampaign(c.id).then(setCamp)}>{c.id}</button>
              <span className="muted small"> {c.settings.symbols.length} pairs · {c.settings.timeframes.join("/")} · {c.passed} passed{c.cancelled ? " · cancelled" : ""}</span></li>)}</ul>
          </>)}
        </section>

        <section>
          {job && job.status !== "done" && (
            <div className="panel howto" role="status" aria-live="polite">
              <h3>{job.status === "running" ? `Campaign: ${job.stage}…` : job.status}</h3>
              {running && <div className="meter"><i style={{ width: `${Math.min(99, (job.done / Math.max(1, job.total)) * 100)}%` }} /></div>}
              <small className="muted">{job.done} / {job.total} steps</small>
              {job.error && <p className="err">{job.error}</p>}
              <pre className="data-log">{job.log.slice(-10).join("\n")}</pre>
            </div>
          )}
          {!camp && !job && <div className="panel"><p className="muted">No campaign yet. Choose the scope and press Run campaign.</p></div>}
          {camp && grid && (
            <>
              <div className="panel opt-head">
                <div>
                  <span className={`verdict ${camp.passed ? "pending" : "fail"}`}>{camp.passed ? `${camp.passed} CANDIDATE(S) PASSED GATE 1 (HOLD-OUT PENDING)` : "NO CANDIDATE PASSED GATE 1"}</span>
                  <h3 style={{ margin: "8px 0 4px" }}>Campaign {camp.id}</h3>
                  <div className="muted small">{camp.baselines.length} baselines · {camp.candidates.length} validated candidates · {camp.started_at.slice(0, 16).replace("T", " ")} → {camp.finished_at.slice(11, 16)} UTC</div>
                  <p style={{ marginTop: 8 }}>{camp.conclusion}</p>
                </div>
              </div>

              <div className="panel">
                <h3>Baselines <small className="muted">profit factor with default settings, in-sample · ★ = shortlisted</small></h3>
                <div className="tablewrap"><table className="tbl heat">
                  <thead><tr><th>Strategy</th>{grid.cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
                  <tbody>{grid.strats.map((st) => (
                    <tr key={st}><td><b>{st}</b></td>{grid.cols.map((c) => {
                      const b = grid.at(st, c);
                      const star = camp.shortlist.some((s) => s.strategy === st && `${s.symbol} ${s.timeframe}` === c);
                      return <td key={c} style={{ background: heat(b?.profit_factor) }} title={b?.error ?? (b ? `${b.trades} trades · return ${b.return_pct}% · DD ${b.max_drawdown_pct}%` : "")}>
                        {b?.error ? "err" : b ? `${pf(b.profit_factor)}${star ? " ★" : ""}` : "—"}<br /><small className="muted">{b?.trades ?? ""}</small></td>;
                    })}</tr>))}
                  </tbody></table></div>
              </div>

              <h3 className="sec">Validated candidates (ranked)</h3>
              <div className="lib-list">
                {camp.candidates.map((c, i) => (
                  <article key={i} className={`panel lib-item ${open === i ? "open" : ""}`}>
                    <button className="lib-row" onClick={() => setOpen(open === i ? null : i)} aria-expanded={open === i}>
                      {open === i ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                      <span className="lib-name"><b>{c.strategy} · {c.symbol} {c.timeframe}</b><small className="muted">{c.source}{c.describe ? `: ${c.describe}` : ""}</small></span>
                      <Verdict v={c.verdict} />
                      <span className="lib-num"><small className="muted">train PF</small><b>{pf(c.train.profit_factor)}</b></span>
                      <span className="lib-num"><small className="muted">valid PF</small><b>{pf(c.validation.profit_factor)}</b></span>
                      <span className="lib-num"><small className="muted">walk-fwd</small><b>{c.walk_forward_efficiency == null ? "—" : `${Math.round(c.walk_forward_efficiency * 100)}%`}</b></span>
                      <span className="lib-num"><small className="muted">fails</small><b>{c.gate1.filter((g) => g.status === "fail").length}</b></span>
                    </button>
                    {open === i && (
                      <div className="lib-body">
                        <div className="small" style={{ margin: "8px 0" }}>Settings: <Params p={c.params} /></div>
                        <GateTable rows={c.gate1} />
                        <div className="lib-actions">
                          {c.library_id && <button className="pill on" onClick={() => nav("/library")}>Open in Strategy Library (run the hold-out there)</button>}
                          {c.strategy !== "RULE" && <button className="pill" onClick={() => nav("/optimizer", { state: { strategy: c.strategy, symbol: c.symbol, timeframe: c.timeframe } })}>Open in Optimiser</button>}
                        </div>
                      </div>
                    )}
                  </article>
                ))}
              </div>
            </>
          )}
        </section>
      </div>
    </>
  );
}
