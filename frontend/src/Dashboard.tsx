import { useCallback, useEffect, useState } from "react";
import { Area, AreaChart, Bar, BarChart, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { RefreshCw } from "lucide-react";
import { type Dash, getDashboard } from "./api";
import "./dashboard.css";

const sign = (n: number) => (n > 0 ? "+" : n < 0 ? "-" : "");
const money = (n: number, plus = false) => `${plus ? sign(n) : n < 0 ? "-" : ""}$${Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 0 })}`;
const short = (n: number) => {
  const a = Math.abs(n), s = n < 0 ? "-" : "";
  return a >= 1e6 ? `${s}${(a / 1e6).toFixed(1)}M` : a >= 1e3 ? `${s}${(a / 1e3).toFixed(a >= 1e4 ? 0 : 1)}K` : `${s}${Math.round(a)}`;
};
const tone = (n: number) => (n > 0 ? "up" : n < 0 ? "down" : "");
const pct = (n: number) => `${Math.round(n * 100)}%`;
const dm = (iso: string) => new Date(iso + "T00:00:00Z").toLocaleDateString("en-GB", { day: "2-digit", month: "short", timeZone: "UTC" }).toUpperCase();
const dlong = (iso: string) => new Date(iso + "T00:00:00Z").toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "short", timeZone: "UTC" });

function Tile({ label, value, sub, cls = "", dashed = false }: { label: string; value: React.ReactNode; sub?: React.ReactNode; cls?: string; dashed?: boolean }) {
  return <div className={`tile ${dashed ? "acct" : ""} ${cls}`}><div className="lbl">{label}</div><div className={`v ${cls === "pos" ? "up" : cls === "neg" ? "down" : ""}`}>{value}</div>{sub && <div className="s">{sub}</div>}</div>;
}

const tipMoney = (v: unknown) => money(Number(v), true);
const lblShort = (v: unknown) => short(Number(v));
const tipStyle = { background: "#171a23", border: "1px solid #30364a", fontSize: 11 };

export default function Dashboard() {
  const [desk, setDesk] = useState(""), [symbol, setSymbol] = useState("");
  const [d, setD] = useState<Dash | null>(null);
  const [err, setErr] = useState(""), [loading, setLoading] = useState(true), [at, setAt] = useState<Date | null>(null);

  const load = useCallback(async (rebuild = false) => {
    setLoading(true); setErr("");
    try { setD(await getDashboard(desk, symbol, rebuild)); setAt(new Date()); }
    catch (e) { setErr((e as Error).message + ". Is the backend running on port 8000?"); }
    finally { setLoading(false); }
  }, [desk, symbol]);
  useEffect(() => { load(); const id = setInterval(() => load(), 60000); return () => clearInterval(id); }, [load]);

  const bar = (
    <div className="dash-bar">
      <select value={desk} onChange={(e) => setDesk(e.target.value)} aria-label="Desk filter">
        <option value="">All desks</option>{(d?.available.desks ?? ["ema", "ict", "smc", "candle"]).map((x) => <option key={x} value={x}>{x} desk</option>)}
      </select>
      <select value={symbol} onChange={(e) => setSymbol(e.target.value)} aria-label="Symbol filter">
        <option value="">All pairs</option>{(d?.available.symbols ?? []).map((x) => <option key={x}>{x}</option>)}
      </select>
      <span className="pill" style={{ color: "#14b8a6" }}>DEMO BOOK</span>
      <span className="sh-spacer" />
      <span className="muted" style={{ fontSize: 10 }}>{at ? `refreshed ${at.toLocaleTimeString()}` : ""}</span>
      <button className="pill" onClick={() => load(true)} title="Rebuild demo ledger"><RefreshCw size={11} className={loading ? "spin" : ""} /> REFRESH</button>
    </div>
  );

  if (err) return <>{bar}<p className="err" role="alert">{err}</p></>;
  if (!d) return <>{bar}<p className="muted">Loading ledger…</p></>;
  if (d.empty) return <>{bar}<div className="banner">{d.warning}</div><div className="panel"><h3>No trades for this filter</h3><p className="muted">
    {desk === "ict" || desk === "smc" ? "The ICT and SMC desks have no strategies yet (Phase 2: structure library)." : "Nothing matches the current filters."}</p></div></>;

  const { career: c, today: t, week: w, month: m, kpis: k } = d;
  const bestMonth = Math.max(...d.months_last_4.map((x) => Math.abs(x.pnl)), 1);
  const wkMax = Math.max(...w.days.map((x) => Math.abs(x.pnl ?? 0)), 1);
  const spark = d.equity.map((e) => ({ date: e.date, v: e.cum }));
  const costTotal = k.costs;
  const dayData = d.days_last_30.map((x) => ({ ...x, label: dm(x.date).slice(0, 2) }));
  const weekData = d.weeks_last_12.map((x) => ({ ...x, label: dm(x.start) }));
  const monthData = d.months_last_4.map((x) => ({ ...x }));

  return (
    <>
      {bar}
      <div className="banner">⚠ {d.warning} ({d.sessions} demo sessions, ${d.initial_capital.toLocaleString()} total demo capital.) Trend regimes are built into the synthetic prices, so profits here prove nothing about real markets.</div>

      <section className={`hero ${c.pnl < 0 ? "neg" : ""}`}>
        <div className="lbl">Career P&L</div>
        <div className={`big ${tone(c.pnl)}`}>{money(c.pnl, true)}</div>
        <div className="sub">since {dm(c.since)} · {c.trades.toLocaleString()} trades · {pct(c.win_rate)} win · {c.trading_days} days · avg {money(c.avg_day, true)}/day · {c.pips.toLocaleString()} pips<br />
          today {money(t.pnl, true)} (booked {money(t.pnl, true)} · floating {money(0)}) · {c.open_positions} open</div>
      </section>

      <div className="sec">Account (forex)</div>
      <div className="grid5">
        {(["Equity", "Balance", "Margin used", "Free margin", "Margin level", "Leverage"] as const).map((l) => (
          <Tile key={l} dashed label={l} value="—" sub={d.account ? "" : "connect MT5 / OANDA"} />
        ))}
      </div>

      <div className="grid4">
        <div className={`tile ${c.pnl >= 0 ? "pos" : "neg"}`}>
          <div className="lbl">Career</div><div className={`v ${tone(c.pnl)}`}>{money(c.pnl, true)}</div>
          <div className="s">since {dm(c.since)} · {c.trades} trades · {pct(c.win_rate)} win</div>
          <ResponsiveContainer width="100%" height={46}><AreaChart data={spark}><Area dataKey="v" stroke="#22c55e" fill="#22c55e33" strokeWidth={1.5} isAnimationActive={false} /><YAxis hide domain={["auto", "auto"]} /></AreaChart></ResponsiveContainer>
        </div>
        <div className={`tile ${t.pnl >= 0 ? "pos" : "neg"}`}>
          <div className="lbl">Today · {dlong(t.date)}</div><div className={`v ${tone(t.pnl)}`}>{money(t.pnl, true)}</div>
          <div className="s">{t.trades} trades · {pct(t.win_rate)} win · {t.pips >= 0 ? "+" : ""}{t.pips} pips<br />
            ▲ {money(t.high, true)} ▼ {money(t.low)} · {t.kept_pct === null ? "kept —" : `kept ${t.kept_pct}%`}</div>
        </div>
        <div className={`tile ${w.pnl >= 0 ? "pos" : "neg"}`}>
          <div className="lbl">This week</div><div className={`v ${tone(w.pnl)}`}>{money(w.pnl, true)}</div>
          <div className="s">{w.trades} trades · <span className={tone(w.vs_last)}>{w.vs_last >= 0 ? "↑" : "↓"} {money(w.vs_last, true)}</span> vs last</div>
          <div className="wkbars">{w.days.map((x) => (
            <div key={x.day}><i style={{ height: x.pnl === null ? 2 : Math.max(3, (Math.abs(x.pnl) / wkMax) * 26), background: x.pnl === null ? "#23232f" : x.pnl >= 0 ? "var(--green)" : "var(--red)" }} />{x.day}</div>
          ))}</div>
        </div>
        <div className={`tile ${m.pnl >= 0 ? "pos" : "neg"}`}>
          <div className="lbl">This month</div><div className={`v ${tone(m.pnl)}`}>{money(m.pnl, true)}</div>
          <div className="s">{m.trades} trades · <span className={tone(m.vs_last)}>{m.vs_last >= 0 ? "↑" : "↓"} {money(m.vs_last, true)}</span> vs last</div>
          <div className="meter"><i style={{ width: `${Math.min(100, (Math.abs(m.pnl) / bestMonth) * 100)}%`, background: m.pnl >= 0 ? "var(--green)" : "var(--red)" }} /></div>
        </div>
      </div>

      <div className="grid5">
        <Tile label="Win rate" value={pct(k.win_rate)} sub={`${c.trades} trades all-time`} />
        <Tile label="Streak" value={k.streak > 0 ? `${k.streak} W` : `${-k.streak} L`} sub={`best run ${k.best_win_run} · worst ${k.worst_loss_run}`} />
        <Tile label="Avg day" value={<span className={tone(k.avg_day)}>{money(k.avg_day, true)}</span>} sub={`over ${c.trading_days} trading days`} />
        <Tile label="Max loss" value={<span className="down">{money(k.max_loss.pnl)}</span>} sub={`${k.max_loss.symbol} · ${dm(k.max_loss.date)}`} />
        <Tile label="Best day" value={<span className="up">{money(k.best_day.pnl, true)}</span>} sub={dlong(k.best_day.date)} />
        <Tile label="Worst day" value={<span className="down">{money(k.worst_day.pnl)}</span>} sub={dlong(k.worst_day.date)} />
        <Tile label="Deepest dip" value={<span className="down">{money(k.deepest_dip)}</span>} sub="from a high water" />
        <Tile label="Long / Short" value={<span className={tone(k.long_pnl)}>{money(k.long_pnl, true)}</span>} sub={<>shorts <span className={tone(k.short_pnl)}>{money(k.short_pnl, true)}</span></>} />
        <Tile label="High water" value={<span className="up">{money(k.high_water.pnl, true)}</span>} sub={`career peak · ${dlong(k.high_water.date)}`} />
        <Tile label="Lowest" value={<span className="down">{money(k.lowest.pnl)}</span>} sub={`career low · ${dlong(k.lowest.date)}`} />
        <Tile label="Profit factor" value={k.profit_factor?.toFixed(2) ?? "—"} sub={`expectancy ${money(k.expectancy, true)}/trade`} />
        <Tile label="W / L" value={`${k.wins}W/${k.losses}L`} sub={`avg ${money(k.avg_win, true)} / ${money(k.avg_loss)}`} />
        <Tile label="Costs" value={<span className="down">-{money(costTotal)}</span>} sub={`≈${money(k.cost_per_trade)}/trade · spread ${money(k.cost_breakdown.spread_cost)} · comm ${money(k.cost_breakdown.commission)} · swap ${money(k.cost_breakdown.swap)} · slip ${money(k.cost_breakdown.slippage_cost)}`} />
        <Tile label="Gross before costs" value={<span className={tone(k.gross_before_costs)}>{money(k.gross_before_costs, true)}</span>} sub="net P&L above is already after costs" />
        <Tile label="Excursion" value={`${k.avg_mfe_pips} / ${k.avg_mae_pips}`} sub={`avg MFE / MAE pips · avg R ${k.avg_r}`} />
      </div>

      <div className="sec">The days · last 30</div>
      <div className="tile"><ResponsiveContainer width="100%" height={200}>
        <BarChart data={dayData} margin={{ top: 16, right: 4, left: 4, bottom: 0 }}>
          <XAxis dataKey="label" stroke="#7a8196" tick={{ fontSize: 9 }} interval={0} /><YAxis hide />
          <Tooltip contentStyle={tipStyle} formatter={tipMoney} labelFormatter={(_, p) => (p[0] ? dlong(p[0].payload.date) : "")} />
          <Bar dataKey="pnl" radius={[3, 3, 0, 0]} isAnimationActive={false}>
            {dayData.map((x, i) => <Cell key={i} fill={x.pnl >= 0 ? "#22c55e" : "#c0443f"} />)}
            <LabelList dataKey="pnl" position="top" formatter={lblShort} style={{ fontSize: 8, fill: "#7a8196" }} />
          </Bar>
        </BarChart></ResponsiveContainer></div>

      <div className="two" style={{ marginTop: 12 }}>
        <div><div className="sec" style={{ marginTop: 0 }}>The weeks · bars</div><div className="tile"><ResponsiveContainer width="100%" height={170}>
          <BarChart data={weekData} margin={{ top: 14, right: 4, left: 4, bottom: 0 }}><XAxis dataKey="label" stroke="#7a8196" tick={{ fontSize: 8 }} interval={0} /><YAxis hide />
            <Tooltip contentStyle={tipStyle} formatter={tipMoney} />
            <Bar dataKey="pnl" radius={[3, 3, 0, 0]} isAnimationActive={false}>{weekData.map((x, i) => <Cell key={i} fill={x.pnl >= 0 ? "#22c55e" : "#c0443f"} />)}
              <LabelList dataKey="pnl" position="top" formatter={lblShort} style={{ fontSize: 8, fill: "#7a8196" }} /></Bar></BarChart></ResponsiveContainer></div></div>
        <div><div className="sec" style={{ marginTop: 0 }}>The months · bars</div><div className="tile"><ResponsiveContainer width="100%" height={170}>
          <BarChart data={monthData} margin={{ top: 14, right: 4, left: 4, bottom: 0 }}><XAxis dataKey="month" stroke="#7a8196" tick={{ fontSize: 9 }} /><YAxis hide />
            <Tooltip contentStyle={tipStyle} formatter={tipMoney} />
            <Bar dataKey="pnl" radius={[3, 3, 0, 0]} isAnimationActive={false}>{monthData.map((x, i) => <Cell key={i} fill={x.pnl >= 0 ? "#22c55e" : "#c0443f"} />)}
              <LabelList dataKey="pnl" position="top" formatter={lblShort} style={{ fontSize: 8, fill: "#7a8196" }} /></Bar></BarChart></ResponsiveContainer></div></div>
      </div>

      <div className="sec">The weeks · last 12</div>
      <div className="scroller">{[...d.weeks_last_12].reverse().map((x) => (
        <div key={x.start} className={`tile ${x.pnl >= 0 ? "pos" : "neg"}`}>
          <div className="lbl">WK {dm(x.start)}</div><div className={`v ${tone(x.pnl)}`}>{money(x.pnl, true)}</div>
          <div className="s">{x.trades}t · {pct(x.win_rate)} win · {x.pips >= 0 ? "+" : ""}{x.pips} pips<br />L <span className={tone(x.long_pnl)}>{money(x.long_pnl, true)}</span> · S <span className={tone(x.short_pnl)}>{money(x.short_pnl, true)}</span></div>
        </div>))}</div>

      <div className="sec">The months · last 4</div>
      <div className="grid4">{[...d.months_last_4].reverse().map((x) => (
        <div key={x.month} className={`tile ${x.pnl >= 0 ? "pos" : "neg"}`}>
          <div className="lbl">{x.month}</div><div className={`v ${tone(x.pnl)}`}>{money(x.pnl, true)}</div>
          <div className="s">{x.trades}t · {pct(x.win_rate)} win · {x.pips >= 0 ? "+" : ""}{x.pips} pips<br />L <span className={tone(x.long_pnl)}>{money(x.long_pnl, true)}</span> · S <span className={tone(x.short_pnl)}>{money(x.short_pnl, true)}</span></div>
        </div>))}</div>

      <div className="two" style={{ marginTop: 12 }}>
        {([["By symbol", d.by_symbol], ["By desk", d.by_desk]] as const).map(([title, rows]) => (
          <div key={title}><div className="sec">{title}</div><div className="tile"><table className="tbl"><thead><tr><th>{title.slice(3)}</th><th>P&L</th><th>Trades</th><th>Win</th><th>Pips</th></tr></thead>
            <tbody>{Object.entries(rows).map(([name, a]) => (<tr key={name}><td>{name.toUpperCase()}</td><td className={tone(a.pnl)}>{money(a.pnl, true)}</td><td>{a.trades}</td><td>{pct(a.win_rate)}</td><td>{a.pips}</td></tr>))}</tbody></table></div></div>
        ))}
      </div>

      <p className="foot">showing demo book · {desk || "all"} desks · {symbol || "all pairs"} · trading day rolls 17:00 New York · history re-reads every 60s</p>
    </>
  );
}
