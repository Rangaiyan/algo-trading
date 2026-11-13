import { useEffect, useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { type Investment as Inv, getInvestment } from "../api";
import { useChartColors } from "../theme";

const usd = (n: number | null | undefined, plus = false) =>
  n == null ? "—" : `${n < 0 ? "-" : plus && n > 0 ? "+" : ""}$${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const pct = (n: number | null | undefined) => (n == null ? "—" : `${n > 0 ? "+" : ""}${n.toFixed(2)}%`);
const tone = (n: number | null | undefined) => (n == null ? "" : n > 0 ? "up" : n < 0 ? "down" : "");

function Card({ l, v, s, t = "" }: { l: string; v: string; s?: string; t?: string }) {
  return <div className="tile"><div className="lbl">{l}</div><div className={`v ${t}`}>{v}</div>{s && <div className="s">{s}</div>}</div>;
}

/** My Investment (doc 15): invested vs current value, TWR / XIRR, equity curve with cash flows, allocation, ledger. */
export default function Investment() {
  const cc = useChartColors();
  const [d, setD] = useState<Inv | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    const load = () => getInvestment().then((x) => { setD(x); setErr(""); }).catch((e) => setErr(e.message));
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, []);

  if (!d) return err ? <div className="banner">{err}</div> : <p className="muted">Loading…</p>;

  return (
    <>
      <section className="desk-head" style={{ ["--dc" as string]: "#22c55e" }}>
        <div className="lbl" style={{ color: "#22c55e" }}>PORTFOLIO</div>
        <h2>My Investment</h2>
        <p className="muted">{d.server} · {d.mode?.toUpperCase()} · {d.currency}. Everything comes from the broker's own records (deposits, withdrawals and closed deals);
          today's point is live equity. TWR measures the strategies (unaffected by when you add money); XIRR is your money-weighted result.</p>
      </section>
      <div className="grid5">
        <Card l="Invested" v={usd(d.invested)} s={`deposits ${usd(d.deposits)} · withdrawals ${usd(d.withdrawals)}`} />
        <Card l="Current value" v={usd(d.current_value)} />
        <Card l="Net profit" v={usd(d.net_profit, true)} s={pct(d.return_pct)} t={tone(d.net_profit)} />
        <Card l="Today" v={usd(d.today_pnl, true)} t={tone(d.today_pnl)} />
        <Card l="TWR / XIRR" v={`${pct(d.twr_pct)} / ${pct(d.xirr_pct)}`} s="time-weighted / money-weighted (annual)" />
        <Card l="Max drawdown" v={pct(d.max_drawdown_pct)} s={`best day ${pct(d.best_day_pct)} · worst ${pct(d.worst_day_pct)}`} t="down" />
      </div>

      <div className="panel">
        <h3>Account value <small className="muted">dots = deposits / withdrawals</small></h3>
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={d.curve}>
            <CartesianGrid stroke={cc.grid} />
            <XAxis dataKey="t" minTickGap={50} stroke={cc.axis} />
            <YAxis stroke={cc.axis} width={70} domain={["auto", "auto"]} />
            <Tooltip contentStyle={{ background: cc.tipBg, border: `1px solid ${cc.tipBorder}`, color: cc.tipText }}
              formatter={(v, n) => [n === "balance" ? usd(Number(v)) : v, n === "balance" ? "Value" : n]} />
            <Area dataKey="balance" stroke={cc.line} fill={cc.line + "22"} strokeWidth={2} isAnimationActive={false}
              dot={(p: { cx?: number; cy?: number; payload?: { cash: number }; index?: number }) => p.payload?.cash
                ? <circle key={p.index} cx={p.cx} cy={p.cy} r={4} fill={p.payload.cash > 0 ? cc.up : cc.down} /> : <g key={p.index} />} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="two">
        <div className="panel">
          <h3>By strategy</h3>
          {d.by_strategy.length === 0 ? <p className="muted">No closed trades yet.</p> : (
            <table className="tbl"><thead><tr><th>Strategy</th><th>Trades</th><th>P&L</th></tr></thead>
              <tbody>{d.by_strategy.map((s) => <tr key={s.strategy}><td>{s.strategy}</td><td>{s.trades}</td><td className={tone(s.pnl)}>{usd(s.pnl, true)}</td></tr>)}</tbody></table>)}
          <h3 style={{ marginTop: 16 }}>By pair</h3>
          {d.by_symbol.length === 0 ? <p className="muted">—</p> : (
            <table className="tbl"><tbody>{d.by_symbol.map((s) => <tr key={s.symbol}><td>{s.symbol}</td><td className={tone(s.pnl)}>{usd(s.pnl, true)}</td></tr>)}</tbody></table>)}
          <p className="muted small" style={{ marginTop: 10 }}>Costs: commission {usd(d.costs.commission)} · swap {usd(d.costs.swap)} · fees {usd(d.costs.fees)}</p>
        </div>
        <div className="panel">
          <h3>Monthly returns</h3>
          <div className="months">{d.monthly_pct.length === 0 ? <span className="muted">—</span> : d.monthly_pct.map((m) => (
            <div key={m.month} className={`month ${m.pct >= 0 ? "g" : "r"}`}><small>{m.month}</small><b>{pct(m.pct)}</b></div>))}</div>
          <h3 style={{ marginTop: 16 }}>Capital ledger</h3>
          <table className="tbl"><thead><tr><th>Date</th><th>Type</th><th>Amount</th></tr></thead>
            <tbody>{d.ledger.map((l, i) => <tr key={i}><td>{l.ts.slice(0, 10)}</td><td>{l.type}</td><td className={tone(l.amount)}>{usd(l.amount, true)}</td></tr>)}</tbody></table>
          <p className="muted small">Deposits and withdrawals are read from the broker. Updated {d.as_of.slice(11, 16)} UTC.</p>
        </div>
      </div>
    </>
  );
}
