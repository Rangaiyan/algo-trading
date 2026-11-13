import { useCallback, useEffect, useState } from "react";
import { OctagonX, Pause, Play, Plus, RefreshCw, Square, Trash2 } from "lucide-react";
import {
  type LibEntry, type RiskConfig, type TradingStatus, addTradeSession, deleteSession, listLibrary, listStrategies,
  resumeTrading, setSessionStatus, tickNow, tradingStatus, updateRisk,
} from "../api";
import KillDialog from "./KillDialog";

const SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD"];
const TFS = ["M15", "H1", "H4"];
const ago = (iso: string | null) => {
  if (!iso) return "never";
  const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  return s < 90 ? `${s}s ago` : s < 5400 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)} h ago`;
};
const usd = (n: number | undefined | null) => (n == null ? "—" : `${n < 0 ? "-" : n > 0 ? "+" : ""}$${Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 2 })}`);

function Meter({ label, value, limit }: { label: string; value?: number; limit?: number }) {
  const used = value != null && limit ? Math.min(100, Math.max(0, (value / limit) * 100)) : 0;
  const tone = used >= 80 ? "var(--red)" : used >= 50 ? "var(--amber)" : "var(--green)";
  return (
    <div className="rmeter">
      <div className="rmeter-top"><span>{label}</span><b className={value != null && value < 0 ? "down" : ""}>{value == null ? "—" : `${value.toFixed(2)}%`}</b></div>
      <div className="meter"><i style={{ width: `${used}%`, background: tone }} /></div>
      <small className="muted">limit {limit}% · {used.toFixed(0)}% used</small>
    </div>
  );
}

/** Live Trading (Phase 5): strategy sessions on the demo account, risk manager, kill switch, order log. */
export default function Trading() {
  const [st, setSt] = useState<TradingStatus | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [kill, setKill] = useState(false);
  const [busy, setBusy] = useState("");
  const [lib, setLib] = useState<LibEntry[]>([]);
  const [strategies, setStrategies] = useState<{ id: string }[]>([]);
  const [add, setAdd] = useState({ from: "library", library_id: "", strategy: "EMA-2", symbol: "EURUSD", timeframe: "H1", ack: false });
  const [risk, setRisk] = useState<Partial<RiskConfig> | null>(null);

  const load = useCallback(() => tradingStatus().then((s) => { setSt(s); setErr(""); }).catch((e) => setErr(e.message)), []);
  useEffect(() => {
    load();
    listLibrary().then(setLib).catch(() => {});
    listStrategies().then(setStrategies).catch(() => {});
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  async function act(what: string, fn: () => Promise<unknown>, ok?: string) {
    setBusy(what); setErr(""); setMsg("");
    try { await fn(); if (ok) setMsg(ok); await load(); }
    catch (e) { setErr((e as Error).message); }
    finally { setBusy(""); }
  }

  if (!st) return <>{err ? <div className="banner">{err}</div> : <p className="muted">Loading…</p>}</>;
  const r = st.risk, halted = r.state.halt, acc = st.account;
  const libChoices = lib.filter((e) => e.status !== "retired");
  const chosen = libChoices.find((e) => e.id === add.library_id);
  const needsAck = add.from === "strategy" || (chosen && !["paper", "validated"].includes(chosen.status));
  const cfg = { ...r.config, ...(risk ?? {}) };

  return (
    <>
      <section className="desk-head trade-head" style={{ ["--dc" as string]: "#ef4444" }}>
        <div>
          <div className="lbl" style={{ color: "#ef4444" }}>PAPER TRADING · DEMO ACCOUNT ONLY</div>
          <h2>Live Trading</h2>
          <p className="muted">Strategy sessions trade your <b>{acc.connected ? `${acc.server} (${acc.mode})` : "MT5"}</b> account on live candles. Every signal passes the risk manager,
            every order carries a broker-side stop-loss, and the gateway refuses any non-demo account. The engine checks every {st.loop_seconds}s
            (last check {ago(st.state.last_tick)}{st.state.connected === false ? ", MT5 NOT CONNECTED" : ""}).</p>
        </div>
        <div className="trade-head-actions">
          <button className="pill" disabled={!!busy} onClick={() => act("tick", tickNow, "Checked now.")}><RefreshCw size={13} className={busy === "tick" ? "spin" : ""} /> Check now</button>
          <button className="kill" onClick={() => setKill(true)}><OctagonX size={16} /> Kill switch</button>
        </div>
      </section>

      {halted && (
        <div className="halt-banner" role="alert">
          <b>TRADING HALTED · {halted.toUpperCase()}</b> — {r.state.halt_reason} {r.state.halted_at && `(${ago(r.state.halted_at)})`}
          {["daily", "weekly"].includes(halted) ? <span className="muted"> · clears automatically at the next trading {halted === "daily" ? "day" : "week"}</span> : null}
          <button className="pill" onClick={() => act("resume", resumeTrading, "Trading resumed. Sessions stay paused until you start them.")}>Resume trading</button>
        </div>
      )}
      {err && <div className="banner">{err}</div>}
      {msg && <div className="note">{msg}</div>}
      {st.state.last_error && <div className="banner">Engine error: {st.state.last_error}</div>}

      <div className="grid5">
        <div className="tile"><div className="lbl">Equity</div><div className="v">{acc.connected ? `$${acc.equity.toLocaleString(undefined, { maximumFractionDigits: 2 })}` : "—"}</div>
          <div className="s">{acc.connected ? `floating ${usd(acc.floating)} · ${acc.positions.length} open` : ""}</div></div>
        <div className="tile"><Meter label="Today" value={r.usage.day_pct} limit={-(r.usage.limits?.day ?? cfg.daily_loss_limit_pct)} /></div>
        <div className="tile"><Meter label="This week" value={r.usage.week_pct} limit={-(r.usage.limits?.week ?? cfg.weekly_loss_limit_pct)} /></div>
        <div className="tile"><Meter label="Drawdown from peak" value={r.usage.drawdown_pct} limit={-(r.usage.limits?.drawdown ?? cfg.max_drawdown_pct)} /></div>
        <div className="tile"><div className="lbl">Execution</div><div className="v">{st.execution.filled}/{st.execution.orders}</div>
          <div className="s">filled · slip {st.execution.avg_slippage_pips ?? "—"} pips · spread {st.execution.avg_spread_pips ?? "—"} · {st.execution.avg_latency_ms ?? "—"} ms · rejected {st.execution.rejected}</div></div>
      </div>

      <div className="panel">
        <h3>Strategy sessions</h3>
        {st.sessions.length === 0 ? <p className="muted">No sessions yet. Add one below. It starts paused; press Start when ready.</p> : (
          <div className="tablewrap"><table className="tbl sess-tbl">
            <thead><tr><th>Session</th><th>Mode</th><th>Status</th><th>Last candle</th><th>Last signal</th><th></th></tr></thead>
            <tbody>{st.sessions.map((s) => (
              <tr key={s.id}>
                <td><b>{s.name}</b><br /><small className="muted">{s.strategy} · {s.symbol} {s.timeframe} · magic {s.magic} · id {s.id}</small>
                  {s.last_error && <><br /><small className="down">{s.last_error}</small></>}</td>
                <td><span className={`status-chip ${s.mode === "paper" ? "validated" : "paper"}`}>{s.mode}</span></td>
                <td><span className={`st ${s.status}`}>{s.status.toUpperCase()}</span></td>
                <td className="small">{s.last_bar ? s.last_bar.slice(0, 16).replace("T", " ") : "—"}</td>
                <td className="small">{s.last_signal ? <>{s.last_signal.side.toUpperCase()} @ {s.last_signal.entry ?? "market"} · SL {s.last_signal.sl}<br /><span className="muted">{s.last_signal.decision ?? s.last_signal.reason}</span></> : <span className="muted">none yet</span>}</td>
                <td className="sess-act">
                  {s.status !== "running" && <button className="pill on" disabled={!!busy} onClick={() => act(`s-${s.id}`, () => setSessionStatus(s.id, "running"))}><Play size={12} /> Start</button>}
                  {s.status === "running" && <button className="pill amber" disabled={!!busy} onClick={() => act(`s-${s.id}`, () => setSessionStatus(s.id, "paused"))}><Pause size={12} /> Pause</button>}
                  {s.status !== "stopped" && <button className="pill" disabled={!!busy} onClick={() => act(`s-${s.id}`, () => setSessionStatus(s.id, "stopped"))}><Square size={12} /> Stop</button>}
                  <button className="pill red" disabled={!!busy} onClick={() => window.confirm(`Delete session “${s.name}”?`) && act(`d-${s.id}`, () => deleteSession(s.id))}><Trash2 size={12} /></button>
                </td>
              </tr>))}
            </tbody></table></div>
        )}

        <h4 className="lib-h">Add a session</h4>
        <div className="add-sess">
          <select value={add.from} onChange={(e) => setAdd({ ...add, from: e.target.value, ack: false })} aria-label="source">
            <option value="library">From the Strategy Library</option><option value="strategy">A built-in strategy (shakedown)</option>
          </select>
          {add.from === "library" ? (
            <select value={add.library_id} onChange={(e) => setAdd({ ...add, library_id: e.target.value, ack: false })} aria-label="library entry">
              <option value="">Choose…</option>
              {libChoices.map((e) => <option key={e.id} value={e.id}>{e.name} · {e.symbol} {e.timeframe} · {e.status}</option>)}
            </select>
          ) : (
            <>
              <select value={add.strategy} onChange={(e) => setAdd({ ...add, strategy: e.target.value })} aria-label="strategy">{strategies.filter((x) => x.id !== "RULE").map((x) => <option key={x.id}>{x.id}</option>)}</select>
              <select value={add.symbol} onChange={(e) => setAdd({ ...add, symbol: e.target.value })} aria-label="pair">{SYMBOLS.map((x) => <option key={x}>{x}</option>)}</select>
              <select value={add.timeframe} onChange={(e) => setAdd({ ...add, timeframe: e.target.value })} aria-label="timeframe">{TFS.map((x) => <option key={x}>{x}</option>)}</select>
            </>
          )}
          {needsAck && (
            <label className="check ack"><input type="checkbox" checked={add.ack} onChange={(e) => setAdd({ ...add, ack: e.target.checked })} />
              <span>Shakedown: this strategy has <b>not</b> passed Gate 1. Run it on the demo account only to test the order path (plan §11.3, weeks 1–2).</span></label>
          )}
          <button className="run" style={{ width: "auto" }} disabled={!!busy || (add.from === "library" && !add.library_id) || (!!needsAck && !add.ack)}
            onClick={() => act("add", () => addTradeSession(add.from === "library"
              ? { library_id: add.library_id, acknowledge_unvalidated: add.ack }
              : { strategy: add.strategy, symbol: add.symbol, timeframe: add.timeframe, acknowledge_unvalidated: add.ack }), "Session added (paused). Press Start to begin.")}>
            <Plus size={14} /> Add session</button>
        </div>
      </div>

      <div className="two">
        <div className="panel">
          <h3>Orders <small className="muted">newest first</small></h3>
          {st.orders.length === 0 ? <p className="muted">No orders yet.</p> : (
            <div className="tablewrap"><table className="tbl">
              <thead><tr><th>Placed</th><th>Session</th><th>Side</th><th>Lots</th><th>Price</th><th>Slip</th><th>State</th><th>P&L</th></tr></thead>
              <tbody>{st.orders.map((o) => (
                <tr key={o.tag} title={o.reason ?? ""}>
                  <td>{o.placed_at.slice(5, 16).replace("T", " ")}</td><td>{o.session_name}</td>
                  <td><span className={`side-badge ${o.side}`}>{o.side === "buy" ? "LONG" : "SHORT"}</span> {o.symbol}</td><td>{o.lots}</td>
                  <td>{o.fill_price ?? o.requested_price}{o.type === "limit" && <small className="muted"> lim</small>}</td>
                  <td>{o.slippage_pips ?? "—"}</td>
                  <td><span className={`ostate ${o.state}`}>{o.state}{o.exit_reason ? ` (${o.exit_reason})` : ""}</span></td>
                  <td className={(o.pnl ?? 0) >= 0 ? "up" : "down"}>{o.pnl == null ? "" : usd(o.pnl)}</td>
                </tr>))}
              </tbody></table></div>
          )}
        </div>
        <div className="panel form">
          <h3>Risk settings</h3>
          <div className="risk-grid">
            {([
              ["risk_pct", "Risk per trade %", 0.05], ["max_risk_pct", "Hard cap per trade %", 0.05], ["daily_loss_limit_pct", "Daily loss limit %", 0.25],
              ["weekly_loss_limit_pct", "Weekly loss limit %", 0.25], ["max_drawdown_pct", "Max drawdown %", 0.5], ["max_open_positions", "Max open positions", 1],
              ["max_per_symbol", "Max per pair", 1], ["max_usd_exposure", "Max same-way USD", 1], ["max_trades_per_day", "Trades/day per session", 1],
              ["min_margin_level_pct", "Min margin level %", 50],
            ] as const).map(([k, label, step]) => (
              <label key={k}>{label}<input type="number" step={step} value={Number(cfg[k])} onChange={(e) => setRisk({ ...(risk ?? {}), [k]: +e.target.value })} /></label>
            ))}
          </div>
          <small className="muted">Max spread (pips): {Object.entries(cfg.max_spread_pips).map(([k, v]) => `${k} ${v}`).join(" · ")}</small>
          <button className="run" style={{ marginTop: 10 }} disabled={!risk || !!busy} onClick={() => act("risk", () => updateRisk(risk!).then(() => setRisk(null)), "Risk settings saved.")}>Save risk settings</button>
          {st.state.issues.length > 0 && (<><h4 className="lib-h">Reconciliation issues</h4><ul className="small">{st.state.issues.slice(-5).map((i) => <li key={i.key}>{i.msg}</li>)}</ul></>)}
          <h4 className="lib-h">Risk events</h4>
          <ul className="small risk-events">{r.state.events.slice(-6).reverse().map((ev, k) => <li key={k}><span className="muted">{ev.at.slice(5, 16).replace("T", " ")}</span> {ev.msg}</li>)}</ul>
        </div>
      </div>
      {kill && <KillDialog onClose={() => setKill(false)} onDone={(m) => { setMsg(m); load(); }} />}
    </>
  );
}
