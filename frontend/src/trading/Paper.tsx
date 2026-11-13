import { useCallback, useEffect, useState } from "react";
import { type Gate2, type NewsEvent, getGate2, getNews, markDrill } from "../api";
import { GateTable, Verdict } from "../research/common";

const usd = (n: number | null | undefined) => (n == null ? "—" : `${n < 0 ? "-" : n > 0 ? "+" : ""}$${Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 2 })}`);
const local = (iso: string) => new Date(iso).toLocaleString(undefined, { weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });

/** Paper trading / Gate 2 (plan §11): paper results vs backtest, execution quality, reliability, failure drills, news. */
export default function Paper() {
  const [g, setG] = useState<Gate2 | null>(null);
  const [news, setNews] = useState<Awaited<ReturnType<typeof getNews>> | null>(null);
  const [err, setErr] = useState("");
  const [notes, setNotes] = useState<Record<string, string>>({});

  const load = useCallback(() => getGate2().then((x) => { setG(x); setErr(""); }).catch((e) => setErr(e.message)), []);
  useEffect(() => {
    load();
    getNews().then((n) => {
      const cutoff = Date.now() - 3600_000;  // keep events from the last hour onwards
      setNews({ ...n, events: n.events.filter((e) => new Date(e.at).getTime() > cutoff) });
    }).catch(() => {});
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, [load]);

  async function drill(key: string, done: boolean) {
    try { await markDrill(key, done, notes[key] ?? ""); await load(); } catch (e) { setErr((e as Error).message); }
  }

  const upcoming: NewsEvent[] = news?.events ?? [];
  return (
    <>
      <section className="desk-head" style={{ ["--dc" as string]: "#f59e0b" }}>
        <div className="lbl" style={{ color: "#f59e0b" }}>PAPER TRADING · GATE 2 · PLAN §11</div>
        <h2>Paper Trading</h2>
        <p className="muted">At least 8 weeks of paper trading on the demo account, with the same code, risk manager and alerts as live. Each session's results are compared
          with what its backtest promised. Gate 2 also needs a clean reconciliation record and all 7 failure drills done. No parameter changes during the test:
          a changed strategy is a new version and restarts its clock.</p>
      </section>
      {err && <div className="banner">{err}</div>}

      {!g ? <p className="muted">Loading…</p> : g.sessions.length === 0 ? (
        <div className="panel"><h3>No paper sessions yet</h3><p className="muted">Paper trading starts when a strategy passes Gate 1 (including its hold-out) and is added on the
          Live Trading page from the Strategy Library. Shakedown sessions are listed here too, but cannot pass Gate 2.</p></div>
      ) : (
        <div className="lib-list">{g.sessions.map((s) => (
          <article key={s.session.id} className="panel">
            <div className="opt-head">
              <div>
                <Verdict v={s.verdict} />
                <h3 style={{ margin: "8px 0 4px" }}>{s.session.name} <small className="muted">· {s.session.mode} · {s.session.status}</small></h3>
                <div className="muted small">Since {s.since.slice(0, 10)} ({s.weeks} weeks) · {s.paper.trades} closed trades · net {usd(s.paper.net)} ·
                  PF {s.paper.profit_factor ?? "—"} · win {s.paper.win_rate == null ? "—" : `${Math.round(s.paper.win_rate * 100)}%`} · avg {s.paper.avg_r ?? "—"}R ·
                  hold {s.paper.avg_hold_hours ?? "—"} h</div>
                {s.expected && <div className="muted small">Backtest promised: PF {s.expected.profit_factor ?? "—"} · win {s.expected.win_rate == null ? "—" : `${Math.round(s.expected.win_rate * 100)}%`} ·
                  {" "}{s.expected.trades_per_week ?? "—"} trades/week · worst-5% drawdown {s.expected.mc_p95_dd_pct ?? "—"}%</div>}
                <div className="muted small">Execution: slippage {s.execution.avg_slippage_pips ?? "—"} pips · spread {s.execution.avg_spread_pips ?? "—"} pips · rejected {s.execution.rejected}</div>
              </div>
            </div>
            <GateTable rows={s.criteria} />
          </article>))}
        </div>
      )}

      <div className="two">
        <div className="panel">
          <h3>Failure drills <small className="muted">plan §11.4 · each must be done at least once</small></h3>
          <ul className="drills">{g?.drills.map((d) => (
            <li key={d.key} className={d.done ? "done" : ""}>
              <label className="check"><input type="checkbox" checked={d.done} onChange={(e) => drill(d.key, e.target.checked)} /> <span>{d.drill}</span></label>
              {d.done ? <small className="muted">done {d.at?.slice(0, 10)}{d.note ? ` · ${d.note}` : ""}</small>
                : <input className="drill-note" placeholder="What happened (optional, saved when you tick it)" value={notes[d.key] ?? ""} onChange={(e) => setNotes({ ...notes, [d.key]: e.target.value })} />}
            </li>))}
          </ul>
        </div>
        <div className="panel">
          <h3>High-impact news <small className="muted">{news ? `filter ${news.filter_on ? "ON" : "OFF"} · ${news.before_min} min before → ${news.after_min} min after` : ""}</small></h3>
          {news?.error && <p className="amb small">Calendar fetch problem: {news.error} (using the last copy)</p>}
          {upcoming.length === 0 ? <p className="muted">No more {news?.impacts.join("/") ?? "high"}-impact events this week.</p> : (
            <table className="tbl"><thead><tr><th>When (your time)</th><th>Cur.</th><th>Event</th><th>Forecast</th></tr></thead>
              <tbody>{upcoming.map((e, i) => <tr key={i}><td>{local(e.at)}</td><td><b>{e.currency}</b></td><td>{e.title}</td><td>{e.forecast || "—"}</td></tr>)}</tbody></table>)}
          <p className="muted small" style={{ marginTop: 8 }}>Source: ForexFactory weekly calendar, refreshed hourly. Settings are on the Live Trading page (risk settings).</p>
        </div>
      </div>
    </>
  );
}
