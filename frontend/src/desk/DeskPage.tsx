import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Archive, FileDown, Pause, Play, Plus, RefreshCw, Rocket, Square, Trophy, X } from "lucide-react";
import { listSessions, sessionAction, type Session } from "../api";
import { DESK_COLORS } from "../nav";
import { activeSessions, fxMarketOpen } from "../sessions";
import LivePanel from "./LivePanel";
import PastTrades from "./PastTrades";
import TradeModal from "./TradeModal";
import { dt, money, pct, tone } from "./format";
import "./desk.css";

export const DESK_INFO: Record<string, { title: string; eyebrow: string; blurb: string; empty?: string }> = {
  ema: { title: "EMA Desk", eyebrow: "TREND", blurb: "Trades EMA trend rules. EMA-1 buys pullbacks to the 20/50 EMA inside an EMA-200 trend with a confirmation candle; EMA-2 trades a fast/slow crossover filtered by ADX. Signals fire on a closed candle and fill at the next open." },
  candle: { title: "Candle Desk", eyebrow: "PATTERNS", blurb: "Baseline candlestick strategy: engulfing and pin-bar patterns in the direction of the EMA-200 trend, stop beyond the pattern, fixed reward-to-risk." },
  ict: { title: "ICT Desk", eyebrow: "TIME & PRICE", blurb: "Kill-zone liquidity raids, optimal trade entry, Silver Bullet windows and the New York open.", empty: "No ICT strategies exist yet. They arrive with the structure library (Phase 2): sweeps, CHoCH, FVG, order blocks and New York kill zones." },
  smc: { title: "SMC Desk", eyebrow: "STRUCTURE", blurb: "Liquidity sweep + CHoCH + order block / FVG entries, BOS continuation and FVG mitigation.", empty: "No SMC strategies exist yet. They arrive with the structure library (Phase 2): swings, BOS/CHoCH, FVG, order blocks and liquidity sweeps." },
};

type View = "cards" | "strip" | "table";

function WinBar({ s }: { s: Session }) {
  const m = s.metrics, w = m.trades ? (m.wins / m.trades) * 100 : 0;
  return <div><div className="winbar" aria-hidden><i style={{ width: `${w}%` }} /></div><div className="s">{m.wins}W / {m.losses}L {pct(m.win_pct)} win · {m.trades} trades</div></div>;
}

function Card({ s, sel, color, onSelect, actions }: { s: Session; sel: boolean; color: string; onSelect: () => void; actions: React.ReactNode }) {
  const m = s.metrics;
  return (
    <article className={`scard ${sel ? "sel" : ""}`} style={{ ["--dc" as string]: color }}>
      <button className="scard-hit" onClick={onSelect} aria-pressed={sel} aria-label={`Select ${s.name}`}>
        <div className="sc-top"><span className="symtag" style={{ color }}>{s.symbol}</span><span className="chip">DEMO</span><span className="sh-spacer" /><span className={`st ${s.status}`}>{s.status.toUpperCase()}</span></div>
        <h4>{s.name}</h4>
        <div className="chips"><span className="chip v">{s.timeframe}</span><span className="chip v">LONG+SHORT</span><span className="chip v">{s.risk_pct}% risk</span>
          {Object.entries(s.settings).map(([k, v]) => <span key={k} className="chip">{k} {v}</span>)}</div>
        <div className={`net ${tone(m.net)}`}>{money(m.net, true)} <small>NET</small></div>
        <div className="two-box"><div><span className="lbl">BOOKED</span><b className={tone(m.booked)}>{money(m.booked, true)}</b><small>{m.trades} closed</small></div>
          <div><span className="lbl">OPEN</span><b>{money(m.open)}</b><small>flat</small></div></div>
        <div className="pl"><span className="up">▲ peak {money(m.peak)}</span><span className="down">▼ low {money(m.low)}</span></div>
        <WinBar s={s} />
        <div className="foot3"><div><span className="lbl">TODAY</span><b className={tone(m.today?.pnl ?? 0)}>{m.today ? money(m.today.pnl, true) : "no trades"}</b></div>
          <div><span className="lbl">{m.prev_day ? m.prev_day.date.slice(5) : "PREV"}</span><b className={tone(m.prev_day?.pnl ?? 0)}>{m.prev_day ? money(m.prev_day.pnl, true) : "—"}</b></div>
          <div><span className="lbl">PER TRADE</span><b className={tone(m.per_trade)}>{money(m.per_trade, true)}</b></div></div>
        {m.since && <div className="s muted">since {dt(m.since)} UTC</div>}
      </button>
      {sel && actions}
    </article>
  );
}

export default function DeskPage({ desk }: { desk: string }) {
  const info = DESK_INFO[desk], color = DESK_COLORS[desk as keyof typeof DESK_COLORS];
  const [sessions, setSessions] = useState<Session[]>([]);
  const [meta, setMeta] = useState<{ warning: string; as_of: string | null } | null>(null);
  const [err, setErr] = useState(""), [loading, setLoading] = useState(true), [note, setNote] = useState("");
  const [view, setView] = useState<View>("cards");
  const [mode, setMode] = useState<"all" | "live" | "demo">("all"), [state, setState] = useState("");
  const [f, setF] = useState({ symbol: "", timeframe: "", strategy: "" });
  const [sp, setSp] = useSearchParams();   // deep links: ?session=<id>&trade=<id>
  const [selId, setSelId] = useState<string | null>(() => sp.get("session"));
  const [detail, setDetail] = useState<number | null>(() => (sp.get("trade") ? Number(sp.get("trade")) : null));
  const [focus, setFocus] = useState<number | null>(() => (sp.get("trade") ? Number(sp.get("trade")) : null));
  const prevDesk = useRef(desk);
  useEffect(() => {
    const next = new URLSearchParams();
    if (selId) next.set("session", selId);
    if (detail !== null) next.set("trade", String(detail));
    if (next.toString() !== sp.toString()) setSp(next, { replace: true });
  }, [selId, detail]); // eslint-disable-line react-hooks/exhaustive-deps
  const [confirmStop, setConfirmStop] = useState(false);
  const [now, setNow] = useState(new Date());
  useEffect(() => { const id = setInterval(() => setNow(new Date()), 30000); return () => clearInterval(id); }, []);

  const load = useCallback(async () => {
    setLoading(true); setErr("");
    try { const r = await listSessions(desk); setSessions(r.sessions); setMeta({ warning: r.warning, as_of: r.as_of }); setSelId((cur) => (cur && r.sessions.some((s) => s.id === cur) ? cur : null)); }
    catch (e) { setErr((e as Error).message + ". Is the backend running on port 8000?"); }
    finally { setLoading(false); }
  }, [desk]);
  useEffect(() => {
    if (prevDesk.current !== desk) { prevDesk.current = desk; setSelId(null); }   // only a real desk change clears the selection (StrictMode-safe)
    setF({ symbol: "", timeframe: "", strategy: "" }); setMode("all"); setState(""); load();
  }, [desk, load]);

  const opts = (k: "symbol" | "timeframe" | "strategy") => [...new Set(sessions.map((s) => s[k]))].sort();
  const shown = useMemo(() => sessions.filter((s) => (mode === "all" || (mode === "demo" ? s.mode === "demo" : s.mode === "live"))
    && (!state || s.status === state) && (!f.symbol || s.symbol === f.symbol) && (!f.timeframe || s.timeframe === f.timeframe) && (!f.strategy || s.strategy === f.strategy)), [sessions, mode, state, f]);
  const sel = sessions.find((s) => s.id === selId) ?? null;
  const cnt = { live: sessions.filter((s) => s.mode === "live").length, demo: sessions.filter((s) => s.mode === "demo").length,
    active: sessions.filter((s) => s.status === "running" || s.status === "paused").length, stopped: sessions.filter((s) => s.status === "stopped").length };
  const chips = [mode !== "all" && { k: "book", l: `BOOK ${mode}`, clear: () => setMode("all") }, state && { k: "state", l: `STATE ${state}`, clear: () => setState("") },
    ...(["symbol", "timeframe", "strategy"] as const).filter((k) => f[k]).map((k) => ({ k, l: `${k.toUpperCase()} ${f[k]}`, clear: () => setF({ ...f, [k]: "" }) }))].filter(Boolean) as { k: string; l: string; clear: () => void }[];

  async function act(a: string) {
    if (!sel) return;
    try { const r = await sessionAction(sel.id, a); setNote(`${sel.name}: ${r.status}`); setConfirmStop(false); await load(); }
    catch (e) { setNote((e as Error).message); }
  }
  const can = (a: string) => !!sel && ({ pause: ["running"], resume: ["paused"], stop: ["running", "paused"], archive: ["stopped"] } as Record<string, string[]>)[a].includes(sel.status);
  const actions = (
    <div className="sc-actions" role="group" aria-label="Session controls">
      <button className="pill" disabled title="PDF reports arrive in the Reports phase"><FileDown size={11} /> PDF</button>
      <button className="pill amber" disabled={!can("pause")} onClick={() => act("pause")}><Pause size={11} /> PAUSE</button>
      <button className="pill" disabled={!can("resume")} onClick={() => act("resume")}><Play size={11} /> RESUME</button>
      {confirmStop ? <><button className="pill red fill-red" onClick={() => act("stop")}>CONFIRM STOP</button><button className="pill" onClick={() => setConfirmStop(false)}>CANCEL</button></>
        : <button className="pill red" disabled={!can("stop")} onClick={() => setConfirmStop(true)}><Square size={11} /> STOP</button>}
      <button className="pill" disabled={!can("archive")} onClick={() => act("archive")}><Archive size={11} /> ARCHIVE</button>
    </div>);

  const live = activeSessions(now).map((s) => s.label);
  const header = (
    <div className="pg-head" style={{ ["--dc" as string]: color }}>
      <div className="pg-icon" style={{ color }}><Rocket size={20} /></div>
      <div style={{ flex: 1 }}><div className="lbl">{info.eyebrow}</div><h1>{info.title}</h1><p>{info.blurb}</p></div>
    </div>);
  const toolbar = (
    <div className="dash-bar">
      <button className="pill" disabled title="Creating sessions arrives with execution (Phase 5)"><Plus size={11} /> NEW SESSION</button>
      <Link className="pill" to="/prebuilt" style={{ color: "var(--cyan)" }}><Rocket size={11} /> PREBUILT & SCHEDULES</Link>
      <Link className="pill" to="/archive" style={{ color: "var(--violet)" }}><Archive size={11} /> ARCHIVE</Link>
      <Link className="pill" to="/edge"><Trophy size={11} /> EDGE</Link>
      <span className="sh-spacer" />
      <span className="muted" style={{ fontSize: 10 }}>{fxMarketOpen(now) ? `market open · ${live.join(" + ") || "between sessions"}` : "market closed (Fri 17:00 → Sun 17:00 NY)"}</span>
      <button className="pill" disabled title="Desk PDF arrives in the Reports phase"><FileDown size={11} /> DESK PDF</button>
      <button className="pill" onClick={load} aria-label="Refresh"><RefreshCw size={11} className={loading ? "spin" : ""} /></button>
    </div>);

  if (info.empty) return <>{header}{toolbar}<div className="panel"><h3>No sessions yet</h3><p className="muted">{info.empty}</p></div></>;

  return (
    <>
      {header}{toolbar}
      {meta && <div className="banner">⚠ {meta.warning}</div>}
      {err && <p className="err" role="alert">{err}</p>}
      <div className="dash-bar">
        <div className="seg">{([["all", `ALL ${sessions.length}`], ["live", `LIVE ${cnt.live}`], ["demo", `DEMO ${cnt.demo}`]] as const).map(([k, l]) => <button key={k} className={mode === k ? "on" : ""} onClick={() => setMode(k)}>{l}</button>)}</div>
        <select value={state} onChange={(e) => setState(e.target.value)} aria-label="State"><option value="">ANY STATE</option><option value="running">Running</option><option value="paused">Paused</option><option value="stopped">Stopped</option></select>
        <span className="chip">ACTIVE {cnt.active}</span><span className="chip">STOPPED {cnt.stopped}</span>
        <span className="sh-spacer" />
        <div className="seg">{(["cards", "strip", "table"] as View[]).map((v) => <button key={v} className={view === v ? "on" : ""} onClick={() => setView(v)}>{v.toUpperCase()}</button>)}</div>
      </div>
      <div className="dash-bar"><span className="lbl">REFINE</span>
        {(["symbol", "timeframe", "strategy"] as const).map((k) => <label key={k} className="muted refine">{k === "strategy" ? "SETUP" : k.toUpperCase()}
          <select aria-label={`Refine by ${k}`} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })}><option value="">Any</option>{opts(k).map((o) => <option key={o}>{o}</option>)}</select></label>)}
        <span className="sh-spacer" /><span className="muted">{shown.length} of {sessions.length} sessions</span></div>
      {chips.length > 0 && <div className="dash-bar"><span className="lbl">SHOWING</span>{chips.map((c) => <button key={c.k} className="chip x" onClick={c.clear}>{c.l} <X size={10} /></button>)}
        <button className="pill" onClick={() => { setMode("all"); setState(""); setF({ symbol: "", timeframe: "", strategy: "" }); }}>CLEAR ALL</button></div>}
      {note && <div className="note" role="status">{note}</div>}

      {loading && !sessions.length && <p className="muted">Loading sessions…</p>}
      {!loading && !shown.length && <div className="panel"><p className="muted">{sessions.length ? "No sessions match these filters." : "No sessions on this desk."}</p></div>}

      {view === "cards" && <div className="sgrid">{shown.map((s) => <Card key={s.id} s={s} sel={s.id === selId} color={color} onSelect={() => { setSelId(s.id === selId ? null : s.id); setConfirmStop(false); setFocus(null); }} actions={actions} />)}</div>}
      {view === "strip" && <div className="strip">{shown.map((s) => (
        <button key={s.id} className={`strow ${s.id === selId ? "sel" : ""}`} onClick={() => setSelId(s.id === selId ? null : s.id)} aria-pressed={s.id === selId}>
          <span className={`st ${s.status}`}>{s.status.toUpperCase()}</span><b>{s.name}</b><span className="sh-spacer" /><span className="muted">{s.metrics.trades} trades · {pct(s.metrics.win_pct)} win</span><b className={tone(s.metrics.net)}>{money(s.metrics.net, true)}</b></button>))}
        {sel && actions}</div>}
      {view === "table" && shown.length > 0 && <div className="tablewrap"><table className="tbl"><thead><tr><th>Session</th><th>State</th><th>TF</th><th>Net</th><th>Trades</th><th>Win</th><th>Peak</th><th>Low</th><th>Today</th><th>Per trade</th></tr></thead>
        <tbody>{shown.map((s) => (<tr key={s.id} className={s.id === selId ? "selrow" : ""} onClick={() => setSelId(s.id === selId ? null : s.id)} style={{ cursor: "pointer" }}>
          <td>{s.name}</td><td><span className={`st ${s.status}`}>{s.status}</span></td><td>{s.timeframe}</td><td className={tone(s.metrics.net)}>{money(s.metrics.net, true)}</td><td>{s.metrics.trades}</td><td>{pct(s.metrics.win_pct)}</td>
          <td className="up">{money(s.metrics.peak)}</td><td className="down">{money(s.metrics.low)}</td><td className={tone(s.metrics.today?.pnl ?? 0)}>{s.metrics.today ? money(s.metrics.today.pnl, true) : "—"}</td><td className={tone(s.metrics.per_trade)}>{money(s.metrics.per_trade, true)}</td></tr>))}</tbody></table>
        {sel && actions}</div>}

      {sel && (<>
        <div className="sec">Selected · {sel.name}</div>
        <LivePanel session={sel} focusTrade={focus} onDetail={setDetail} />
        <PastTrades sessionId={sel.id} startBalance={sel.initial_balance} onDetail={setDetail} />
        <section className="panel"><div className="lbl">THE RECORD</div><p className="muted">{sel.symbol} · {sel.name} since {dt(sel.metrics.since ?? sel.started_at)} UTC · {sel.metrics.trades} trades · {pct(sel.metrics.win_pct)} win · booked {money(sel.metrics.booked, true)} · net now <b className={tone(sel.metrics.net)}>{money(sel.metrics.net, true)}</b> · {sel.metrics.pips} pips</p></section>
      </>)}
      {!sel && shown.length > 0 && <p className="muted" style={{ marginTop: 14 }}>Select a session to see its chart, trades and controls.</p>}
      {detail !== null && <TradeModal tradeId={detail} onClose={() => setDetail(null)} onLocate={(t) => { setSelId(t.session_id); setFocus(t.id); }} />}
    </>
  );
}
