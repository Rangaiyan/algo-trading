import { useEffect, useMemo, useState } from "react";
import { Eye, EyeOff, Settings2, Tags } from "lucide-react";
import { getChart, getTrade, type ChartData, type Session, type TradeRow } from "../api";
import Chart, { type Line } from "./Chart";
import { dt, money, price, tone } from "./format";

export default function LivePanel({ session, focusTrade, onDetail }: { session: Session; focusTrade: number | null; onDetail: (id: number) => void }) {
  const [chart, setChart] = useState<ChartData | null>(null);
  const [err, setErr] = useState(""), [show, setShow] = useState(true), [labels, setLabels] = useState(true), [cfg, setCfg] = useState(false);
  const [sel, setSel] = useState<TradeRow | null>(null);
  const [around, setAround] = useState<number | undefined>(undefined);
  const m = session.metrics;

  useEffect(() => { setAround(focusTrade ?? undefined); }, [focusTrade, session.id]);
  useEffect(() => {
    let dead = false; setErr("");
    getChart(session.id, around).then((c) => !dead && setChart(c)).catch((e) => !dead && setErr(e.message));
    return () => { dead = true; };
  }, [session.id, around]);
  useEffect(() => { if (around) getTrade(around).then((d) => setSel(d.trade)).catch(() => setSel(null)); else setSel(null); }, [around]);

  const lines = useMemo<Line[]>(() => sel ? [
    { price: sel.entry_px, color: "#4f8cff", title: "ENTRY" }, { price: sel.stop_loss, color: "#ef4444", title: "STOP" },
    ...(sel.take_profit ? [{ price: sel.take_profit, color: "#22c55e", title: "TARGET" }] : []),
  ] : [], [sel]);

  const jump = chart?.markers.filter((x) => x.kind === "exit").slice(-30).reverse() ?? [];
  return (
    <section className="panel live">
      <div className="live-sum">
        <div><div className="lbl">{session.name}</div><div className="live-title">Flat · no open position on {session.symbol}</div>
          <span className={`st ${session.status}`}>{session.status.toUpperCase()}</span> <span className="chip">DEMO</span> <span className="muted">{session.strategy} · {session.timeframe}</span></div>
        <div className="stat"><div className="lbl">Open now</div><b>{money(m.open)}</b><div className="s">flat</div></div>
        <div className="stat"><div className="lbl">Booked today</div><b className={tone(m.today?.pnl ?? 0)}>{money(m.today?.pnl ?? 0, true)}</b><div className="s">{m.today ? `${m.today.wins}W/${m.today.losses}L` : "no trades"}</div></div>
        <div className="stat"><div className="lbl">{session.symbol}</div><b>{chart ? price(session.symbol, chart.last_price) : "—"}</b><div className="s">last close · simulated</div></div>
        <div className="stat"><div className="lbl">Net (session)</div><b className={tone(m.net)}>{money(m.net, true)}</b><div className="s">{m.trades} trades</div></div>
      </div>
      <div className="live-tools">
        <span className="lbl">VIEW</span>
        <button className={`pill ${show ? "on" : ""}`} onClick={() => setShow(!show)}>{show ? <EyeOff size={11} /> : <Eye size={11} />} {show ? "HIDE CHART" : "SHOW CHART"}</button>
        <button className={`pill ${labels ? "on" : ""}`} onClick={() => setLabels(!labels)}><Tags size={11} /> LABELS {labels ? "ON" : "OFF"}</button>
        <button className={`pill ${cfg ? "on" : ""}`} onClick={() => setCfg(!cfg)}><Settings2 size={11} /> SETTINGS</button>
        <span className="sh-spacer" />
        <label className="muted">JUMP TO <select value={around ?? ""} onChange={(e) => setAround(e.target.value ? Number(e.target.value) : undefined)} aria-label="Jump to trade">
          <option value="">latest</option>{jump.map((j) => <option key={j.trade_id} value={j.trade_id}>{new Date(j.time * 1000).toISOString().slice(5, 16).replace("T", " ")} · {j.side === "buy" ? "LONG" : "SHORT"} {money(j.pnl, true)}</option>)}</select></label>
      </div>
      {cfg && <div className="cfg">{Object.entries({ strategy: session.strategy, symbol: session.symbol, timeframe: session.timeframe, sides: session.sides, "risk per trade": `${session.risk_pct}%`, "start balance": money(session.initial_balance), ...session.settings }).map(([k, v]) => <span key={k}><span className="muted">{k}</span> {String(v)}</span>)}</div>}
      <div className="live-main">
        <div className="live-chart">
          {err && <p className="err" role="alert">{err}</p>}
          {show ? (chart ? <Chart data={chart} labels={labels} lines={lines} selectedTrade={around ?? null} onTradeClick={(id) => { setAround(id); onDetail(id); }} /> : !err && <p className="muted">Loading chart…</p>) : <p className="muted">Chart hidden.</p>}
          <div className="muted s">▲ buy entry ▼ sell entry ● exit (green profit, red loss). Click a marker for the trade detail. Prices are simulated demo data.</div>
        </div>
        <aside className="poscard">
          {sel ? (<>
            <div className="lbl">SELECTED TRADE</div>
            <div className="tc-top"><span className={`side-badge ${sel.side}`}>{sel.side === "buy" ? "LONG" : "SHORT"}</span><b>{sel.symbol}</b><span className="sh-spacer" /><b className={tone(sel.pnl)}>{money(sel.pnl, true)}</b></div>
            <dl><dt>entry</dt><dd>{price(sel.symbol, sel.entry_px)}</dd><dt>exit</dt><dd>{price(sel.symbol, sel.exit_px)}</dd><dt>stop</dt><dd>{price(sel.symbol, sel.stop_loss)}</dd>
              <dt>target</dt><dd>{sel.take_profit ? price(sel.symbol, sel.take_profit) : "—"}</dd><dt>peak profit</dt><dd className="up">{money(sel.peak_profit)}</dd><dt>given back</dt><dd className="amb">{money(sel.given_back)}</dd>
              <dt>kept of best</dt><dd>{sel.kept_pct}%</dd><dt>lots</dt><dd>{sel.qty}</dd><dt>in</dt><dd>{dt(sel.entry_ts)}</dd></dl>
            <button className="pill" onClick={() => onDetail(sel.id)}>FULL DETAIL</button>
          </>) : (<>
            <div className="lbl">POSITION</div><p className="muted">No open position. Demo trades are simulated end to end, so every trade is already closed. Pick one with JUMP TO or click a marker.</p>
            <button className="pill" disabled title="Closing live positions arrives with execution (Phase 5)">CLOSE POSITION</button></>)}
        </aside>
      </div>
    </section>
  );
}
