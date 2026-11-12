import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Area, AreaChart, ResponsiveContainer, YAxis } from "recharts";
import { ChevronDown, ChevronRight, Search } from "lucide-react";
import { getTrades, type TradeRow } from "../api";
import { dLong, dt, held, money, pct, pips, price, tone, tradingDay } from "./format";

type View = "cards" | "table" | "ledger" | "calendar";
const dayOf = tradingDay;   // FX trading day (17:00 New York roll), identical to the Dashboard

export default function PastTrades({ sessionId, startBalance, onDetail }: { sessionId: string; startBalance: number; onDetail: (id: number) => void }) {
  const [open, setOpen] = useState(true);
  const [view, setView] = useState<View>("cards");
  const [basis, setBasis] = useState<"entered" | "exited">("exited");
  const [q, setQ] = useState(""), [qd, setQd] = useState("");
  const [side, setSide] = useState(""), [result, setResult] = useState(""), [day, setDay] = useState("");
  const [rows, setRows] = useState<TradeRow[]>([]);
  const [meta, setMeta] = useState({ total: 0, net: 0, wins: 0 });
  const [err, setErr] = useState(""), [loading, setLoading] = useState(false);
  const [sort, setSort] = useState<{ k: keyof TradeRow; dir: 1 | -1 }>({ k: "exit_ts", dir: -1 });
  const [month, setMonth] = useState<string | null>(null);

  useEffect(() => { const t = setTimeout(() => setQd(q), 250); return () => clearTimeout(t); }, [q]);
  useEffect(() => {
    let dead = false;
    setLoading(true); setErr("");
    getTrades({ session_id: sessionId, side, result, q: qd, basis, limit: 5000 })
      .then((r) => { if (!dead) { setRows(r.trades); setMeta({ total: r.total, net: r.net, wins: r.wins }); } })
      .catch((e) => !dead && setErr(e.message)).finally(() => !dead && setLoading(false));
    return () => { dead = true; };
  }, [sessionId, side, result, qd, basis]);
  useEffect(() => { setDay(""); setMonth(null); }, [sessionId]);

  const key = basis === "exited" ? "exit_ts" : "entry_ts";
  const days = useMemo(() => [...new Set(rows.map((r) => dayOf(r[key])))].sort().reverse(), [rows, key]);
  const shown = useMemo(() => (day ? rows.filter((r) => dayOf(r[key]) === day) : rows), [rows, day, key]);
  const net = shown.reduce((a, r) => a + r.pnl, 0), wins = shown.filter((r) => r.pnl > 0).length;
  const spark = useMemo(() => { let c = 0; return [...shown].reverse().map((r) => ({ v: (c += r.pnl) })); }, [shown]);
  const groups = useMemo(() => {
    const m = new Map<string, TradeRow[]>();
    shown.forEach((r) => { const d = dayOf(r[key]); m.set(d, [...(m.get(d) ?? []), r]); });
    return [...m.entries()];
  }, [shown, key]);
  const sorted = useMemo(() => [...shown].sort((a, b) => (a[sort.k]! > b[sort.k]! ? 1 : -1) * sort.dir), [shown, sort]);
  const ledger = useMemo(() => { let bal = startBalance; return [...shown].reverse().map((r) => ({ ...r, bal: (bal += r.pnl) })).reverse(); }, [shown, startBalance]);
  const sortBy = (k: keyof TradeRow) => setSort((s) => ({ k, dir: s.k === k ? (-s.dir as 1 | -1) : -1 }));

  const cal = useMemo(() => {
    const byDay = new Map<string, { pnl: number; n: number }>();
    rows.forEach((r) => { const d = dayOf(r[key]); const c = byDay.get(d) ?? { pnl: 0, n: 0 }; byDay.set(d, { pnl: c.pnl + r.pnl, n: c.n + 1 }); });
    const months = [...new Set([...byDay.keys()].map((d) => d.slice(0, 7)))].sort().reverse();
    return { byDay, months };
  }, [rows, key]);
  const curMonth = month ?? cal.months[0];

  return (
    <section className="panel pt">
      <button className="pt-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}<b>FIND A PAST TRADE</b><span className="muted">{meta.total} on this session</span>
      </button>
      {open && (<>
        <div className="pt-bar">
          <label className="search"><Search size={12} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="symbol, long/short, date, exit reason…" aria-label="Search trades" /></label>
          <div className="seg" role="tablist">{(["cards", "table", "ledger", "calendar"] as View[]).map((v) => <button key={v} role="tab" aria-selected={view === v} className={view === v ? "on" : ""} onClick={() => setView(v)}>{v.toUpperCase()}</button>)}</div>
          <Link to="/analytics" className="pill" style={{ color: "var(--violet)" }}>ANALYTICS</Link>
        </div>
        <div className="pt-bar">
          <div className="seg"><button className={basis === "entered" ? "on" : ""} onClick={() => setBasis("entered")}>ENTERED</button><button className={basis === "exited" ? "on" : ""} onClick={() => setBasis("exited")}>EXITED</button></div>
          <select value={day} onChange={(e) => setDay(e.target.value)} aria-label="Day filter"><option value="">Any day ({days.length} with trades)</option>{days.map((d) => <option key={d} value={d}>{dLong(d)}</option>)}</select>
          <select value={side} onChange={(e) => setSide(e.target.value)} aria-label="Side filter"><option value="">Long + short</option><option value="buy">Long only</option><option value="sell">Short only</option></select>
          <select value={result} onChange={(e) => setResult(e.target.value)} aria-label="Result filter"><option value="">Wins + losses</option><option value="win">Wins</option><option value="loss">Losses</option></select>
          <span className="sh-spacer" />
          <div style={{ width: 90, height: 26 }}><ResponsiveContainer><AreaChart data={spark}><YAxis hide domain={["auto", "auto"]} /><Area dataKey="v" stroke={net >= 0 ? "#22c55e" : "#ef4444"} fill="none" strokeWidth={1.5} isAnimationActive={false} /></AreaChart></ResponsiveContainer></div>
          <span className="muted">{shown.length} of {meta.total}</span><b className={tone(net)}>{money(net, true)}</b><span className="muted">· {shown.length ? pct(wins / shown.length) : "0%"} win</span>
        </div>
        {err && <p className="err" role="alert">{err}</p>}
        {loading && <p className="muted">Loading trades…</p>}
        {!loading && !shown.length && <p className="muted">No trades match these filters.</p>}

        {view === "cards" && groups.map(([d, rs]) => (
          <div key={d}>
            <div className="day-head"><b>{dLong(d)}</b><span className="muted">{rs.length} trade{rs.length > 1 ? "s" : ""}</span><span className="sh-spacer" /><b className={tone(rs.reduce((a, r) => a + r.pnl, 0))}>{money(rs.reduce((a, r) => a + r.pnl, 0), true)}</b></div>
            <div className="tcards">{rs.map((t) => (
              <article key={t.id} className={`tcard ${t.pnl >= 0 ? "w" : "l"}`}>
                <div className="tc-top"><span className={`side-badge ${t.side}`}>{t.side === "buy" ? "LONG" : "SHORT"}</span><b>{t.symbol}</b><span className="sh-spacer" /><b className={tone(t.pnl)}>{money(t.pnl, true)}</b></div>
                <div className="tc-px">{price(t.symbol, t.entry_px)} → {price(t.symbol, t.exit_px)} <span className={`chip ${tone(t.pips)}`}>{pips(t.pips)} pips</span></div>
                <div className="tc-grid"><span className="lbl">IN</span><span>{dt(t.entry_ts)}</span><span className="lbl">OUT</span><span>{dt(t.exit_ts)}</span>
                  <span className="lbl">HELD</span><span>{held(t.held_minutes)}{t.overnight ? " · o/n" : ""}</span><span className="lbl">LOTS</span><span>{t.qty}</span></div>
                <div className="lbl">KEPT OF ITS BEST {t.kept_pct}%</div><div className="meter"><i style={{ width: `${t.kept_pct}%` }} /></div>
                <div className="tc-foot"><span className="up">peak {money(t.peak_profit)}</span><span className="amb">gave back {money(t.given_back)}</span></div>
                <div className="tc-foot"><span className="chip">{t.exit_reason.toUpperCase()}</span><span className="muted">{t.entry_session}</span><button className="link" onClick={() => onDetail(t.id)}>DETAIL</button></div>
              </article>))}</div>
          </div>))}

        {view === "table" && shown.length > 0 && (
          <div className="tablewrap"><table className="tbl"><thead><tr>
            {([["entry_ts", "Entry"], ["exit_ts", "Exit"], ["side", "Side"], ["qty", "Lots"], ["pips", "Pips"], ["r_multiple", "R"], ["mfe_pips", "MFE"], ["mae_pips", "MAE"], ["exit_reason", "Reason"], ["pnl", "P&L"]] as [keyof TradeRow, string][]).map(([k, l]) =>
              <th key={k} onClick={() => sortBy(k)} aria-sort={sort.k === k ? (sort.dir === 1 ? "ascending" : "descending") : "none"} style={{ cursor: "pointer" }}>{l}{sort.k === k ? (sort.dir === 1 ? " ▴" : " ▾") : ""}</th>)}<th /></tr></thead>
            <tbody>{sorted.map((t) => (<tr key={t.id}><td>{dt(t.entry_ts)}</td><td>{dt(t.exit_ts)}</td><td className={t.side === "buy" ? "up" : "down"}>{t.side === "buy" ? "LONG" : "SHORT"}</td><td>{t.qty}</td><td className={tone(t.pips)}>{pips(t.pips)}</td>
              <td className={tone(t.r_multiple)}>{t.r_multiple.toFixed(2)}</td><td>{t.mfe_pips.toFixed(1)}</td><td>{t.mae_pips.toFixed(1)}</td><td>{t.exit_reason}</td><td className={tone(t.pnl)}>{money(t.pnl, true)}</td>
              <td><button className="link" onClick={() => onDetail(t.id)}>DETAIL</button></td></tr>))}</tbody></table></div>)}

        {view === "ledger" && shown.length > 0 && (
          <div className="tablewrap"><table className="tbl"><thead><tr><th>Closed</th><th>Symbol</th><th>Side</th><th>Gross</th><th>Costs</th><th>Net</th><th>Balance</th><th /></tr></thead>
            <tbody>{ledger.map((t) => (<tr key={t.id}><td>{dt(t.exit_ts)}</td><td>{t.symbol}</td><td className={t.side === "buy" ? "up" : "down"}>{t.side === "buy" ? "LONG" : "SHORT"}</td>
              <td className={tone(t.gross_pnl)}>{money(t.gross_pnl, true)}</td><td className="down">-{money(t.total_costs)}</td><td className={tone(t.pnl)}>{money(t.pnl, true)}</td><td>{money(t.bal)}</td>
              <td><button className="link" onClick={() => onDetail(t.id)}>DETAIL</button></td></tr>))}</tbody></table></div>)}

        {view === "calendar" && curMonth && (() => {
          const [y, m] = curMonth.split("-").map(Number);
          const first = new Date(Date.UTC(y, m - 1, 1)), dim = new Date(Date.UTC(y, m, 0)).getUTCDate(), lead = (first.getUTCDay() + 6) % 7;
          const cells = [...Array(lead).fill(null), ...Array.from({ length: dim }, (_, i) => i + 1)];
          return (<div>
            <div className="pt-bar"><select value={curMonth} onChange={(e) => setMonth(e.target.value)} aria-label="Month">{cal.months.map((mo) => <option key={mo}>{mo}</option>)}</select><span className="muted">click a day to filter</span></div>
            <div className="cal">{["M", "T", "W", "T", "F", "S", "S"].map((d, i) => <div key={i} className="cal-h">{d}</div>)}
              {cells.map((c, i) => { if (c === null) return <div key={i} />; const id = `${curMonth}-${String(c).padStart(2, "0")}`, v = cal.byDay.get(id);
                return <button key={i} className={`cal-d ${v ? (v.pnl >= 0 ? "g" : "r") : ""} ${day === id ? "sel" : ""}`} disabled={!v} onClick={() => { setDay(day === id ? "" : id); setView("cards"); }}>
                  <b>{c}</b>{v && <><span>{money(v.pnl, true)}</span><small>{v.n}T</small></>}</button>; })}</div></div>);
        })()}
      </>)}
    </section>
  );
}
