import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, FlaskConical, Trash2 } from "lucide-react";
import { type LibEntry, type LibFull, deleteEntry, getLibrary, listLibrary, promoteEntry, runHoldout } from "../api";
import { GateTable, MetricRows, Params, Verdict } from "./common";
import { pf } from "./format";

const FLOW = ["draft", "backtested", "validated", "paper", "live", "retired"];
const NEXT_LABEL: Record<string, string> = { backtested: "Mark backtested", validated: "Promote to validated", paper: "Start paper trading", retired: "Retire" };

function allowedNext(e: LibEntry): string[] {
  const out: string[] = [];
  if (e.status === "backtested" && e.verdict === "pass") out.push("validated");
  if (e.status === "validated") out.push("paper");
  if (e.status !== "retired") out.push("retired");
  return out;
}

/** Strategy Library (doc 9.4): every validated candidate with its reports, status and history. */
export default function Library() {
  const [rows, setRows] = useState<LibEntry[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [full, setFull] = useState<LibFull | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(() => listLibrary().then((x) => { setRows(x); setErr(""); }).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!open) return;
    let dead = false;
    getLibrary(open).then((x) => { if (!dead) setFull(x); }).catch((e) => { if (!dead) setErr(e.message); });
    return () => { dead = true; };
  }, [open]);

  async function act(fn: () => Promise<unknown>, what: string) {
    setBusy(what); setErr("");
    try { await fn(); await load(); if (open) setFull(await getLibrary(open)); }
    catch (e) { setErr((e as Error).message); }
    finally { setBusy(""); }
  }

  function holdout(e: LibEntry) {
    const msg = e.holdout_used
      ? "The hold-out was ALREADY used for this strategy. Running it again means it is no longer an independent test. Run it anyway?"
      : "Run the hold-out test now? This uses the last 6 months that no optimisation has ever seen. It should be run ONCE: don't tune the strategy afterwards and test again.";
    if (window.confirm(msg)) act(() => runHoldout(e.id, e.holdout_used), `holdout-${e.id}`);
  }

  return (
    <>
      <section className="desk-head" style={{ ["--dc" as string]: "#8b5cf6" }}>
        <div className="lbl" style={{ color: "#8b5cf6" }}>STRATEGY LIBRARY</div>
        <h2>Strategy Library</h2>
        <p className="muted">Strategies saved from the Optimiser or the Rule Builder, with their full validation reports. Each one moves through
          {" "}<b>{FLOW.join(" → ")}</b>. Promotion to <b>validated</b> needs Gate 1 to pass, including the one-time hold-out test. <b>Live</b> needs Gate 2 (paper trading, Phase 5).</p>
      </section>
      {err && <div className="banner">{err}</div>}
      {!rows ? <p className="muted">Loading…</p> : rows.length === 0 ? (
        <div className="panel"><h3>No strategies saved yet</h3><p className="muted">Run the Optimiser and press “Save to library”, or save a rule from the Rule Builder.</p></div>
      ) : (
        <div className="lib-list">
          {rows.map((e) => {
            const isOpen = open === e.id;
            return (
              <article key={e.id} className={`panel lib-item ${isOpen ? "open" : ""}`}>
                <button className="lib-row" onClick={() => setOpen(isOpen ? null : e.id)} aria-expanded={isOpen}>
                  {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  <span className="lib-name"><b>{e.name}</b><small className="muted">{e.strategy} · {e.symbol} {e.timeframe}</small></span>
                  <span className={`status-chip ${e.status}`}>{e.status}</span>
                  <Verdict v={e.verdict} />
                  <span className="lib-num"><small className="muted">in-sample PF</small><b>{pf(e.insample?.profit_factor)}</b></span>
                  <span className="lib-num"><small className="muted">validation PF</small><b>{pf(e.validation?.profit_factor)}</b></span>
                  <span className="lib-num"><small className="muted">hold-out</small><b>{e.holdout ? `${e.holdout.net_profit >= 0 ? "+" : ""}${Math.round(e.holdout.net_profit)}$` : "—"}</b></span>
                </button>
                {isOpen && full?.id === e.id && (
                  <div className="lib-body">
                    <div className="lib-actions">
                      <button className="pill" onClick={() => holdout(e)} disabled={!!busy || !full.report}><FlaskConical size={13} /> {e.holdout_used ? "Re-run hold-out" : "Run hold-out test (once)"}</button>
                      {allowedNext(e).map((to) => (
                        <button key={to} className={`pill ${to === "retired" ? "red" : "on"}`} disabled={!!busy}
                          onClick={() => act(() => promoteEntry(e.id, to), `promote-${to}`)}>{NEXT_LABEL[to]}</button>
                      ))}
                      {e.status === "backtested" && e.verdict !== "pass" && <span className="muted small">Validation is locked until Gate 1 passes.</span>}
                      <span className="sh-spacer" />
                      <button className="pill red" disabled={!!busy} onClick={() => window.confirm(`Delete “${e.name}”? This removes its reports too.`) && act(() => deleteEntry(e.id).then(() => setOpen(null)), "delete")}><Trash2 size={13} /> Delete</button>
                    </div>
                    {busy && <p className="muted small">Working… {busy.startsWith("holdout") && "running the hold-out backtest"}</p>}
                    <div className="small" style={{ margin: "6px 0 12px" }}>Settings: <Params p={full.params} /></div>
                    {full.report ? (
                      <>
                        <GateTable rows={full.report.gate1} />
                        <div style={{ marginTop: 12 }}>
                          <MetricRows rows={[
                            { label: "Training", m: full.report.train }, { label: "Validation", m: full.report.validation },
                            { label: "In-sample", m: full.report.insample },
                            { label: "Hold-out", m: full.report.holdout, note: full.report.holdout ? `(${full.report.holdout.period.join(" → ")})` : "" },
                          ]} />
                        </div>
                      </>
                    ) : <p className="muted">Draft: no validation report yet. Open it in the Optimiser (set settings to try = 0 to validate as-is).</p>}
                    <h4 className="lib-h">History</h4>
                    <ol className="lib-hist">{full.history.map((h, i) => <li key={i}><span className={`status-chip ${h.status}`}>{h.status}</span> <span className="muted">{h.at.replace("T", " ").slice(0, 16)}</span> {h.note}</li>)}</ol>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </>
  );
}
