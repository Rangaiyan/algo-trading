import { useEffect, useState } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getLiveAccount, type LiveAccount as Acct } from "./api";
import { useChartColors } from "./theme";

const fmt = (n: number, cur = "USD", plus = false) => {
  const s = Math.abs(n).toLocaleString(undefined, { style: "currency", currency: cur, minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${n < 0 ? "−" : plus && n > 0 ? "+" : ""}${s}`;
};
const tone = (n: number) => (n > 0 ? "up" : n < 0 ? "down" : "");
const when = (iso: string) => new Date(iso).toLocaleString(undefined, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
const Side = ({ s }: { s: "buy" | "sell" }) => <span className={`side-badge ${s}`}>{s === "buy" ? "Long" : "Short"}</span>;

/** Real MT5 account: equity and its history, realised P&L, open positions and recent closed trades. Refreshes every 10 s. */
export default function LiveAccount() {
  const cc = useChartColors();
  const [a, setA] = useState<Acct | null>(null);
  const [err, setErr] = useState("");
  const [at, setAt] = useState<Date | null>(null);

  useEffect(() => {
    let dead = false;
    const load = async () => {
      try { const d = await getLiveAccount(); if (!dead) { setA(d); setErr(""); setAt(new Date()); } }
      catch (e) { if (!dead) setErr((e as Error).message); }
    };
    load();
    const id = setInterval(load, 10000);
    return () => { dead = true; clearInterval(id); };
  }, []);

  if (err && !a) return <div className="panel empty-state"><h3>Can't reach the backend</h3><p className="muted">{err}. Start it with <code>backend\start.ps1</code>, then this page reconnects by itself.</p></div>;
  if (!a) return <div className="panel empty-state"><p className="muted">Connecting to your MT5 account…</p></div>;
  if (!a.connected) return <div className="panel empty-state"><h3>MT5 account not connected</h3><p className="muted">{a.detail}</p></div>;

  const cur = a.currency;
  const p = a.pnl;
  const total = a.total_pnl ?? 0;
  const curve = [...(a.balance_curve ?? []).map((x) => ({ t: x.t, v: x.balance })), ...(at ? [{ t: at.toISOString(), v: a.equity }] : [])];
  const lineColor = total < 0 ? cc.down : cc.line;

  return (
    <>
      <div className="acct">
        <section className="panel acct-equity" aria-label="Account equity">
          <div className="acct-top">
            <div>
              <div className="k">Equity</div>
              <div className="acct-big num">{fmt(a.equity, cur)}</div>
              <div className={`acct-delta num ${tone(total)}`}>
                {a.total_pnl !== undefined ? fmt(total, cur, true) : "—"}
                {a.return_pct != null && <span> ({a.return_pct > 0 ? "+" : ""}{a.return_pct}%)</span>}
                <span className="muted"> since first deposit</span>
              </div>
            </div>
            <dl className="acct-facts">
              <div><dt>Balance</dt><dd className="num">{fmt(a.balance, cur)}</dd></div>
              <div><dt>Floating</dt><dd className={`num ${tone(a.floating)}`}>{fmt(a.floating, cur, true)}</dd></div>
              <div><dt>Account</dt><dd>{a.server}, {a.mode}, 1:{a.leverage}</dd></div>
            </dl>
          </div>
          <div className="acct-chart">
            <ResponsiveContainer width="100%" height="100%" minHeight={130}>
              <AreaChart data={curve} margin={{ top: 8, right: 0, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="eqfill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={lineColor} stopOpacity={0.22} />
                    <stop offset="100%" stopColor={lineColor} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="t" hide />
                <YAxis hide domain={["dataMin - 50", "dataMax + 50"]} />
                <Tooltip contentStyle={{ background: cc.tipBg, border: `1px solid ${cc.tipBorder}`, color: cc.tipText, borderRadius: 8 }}
                  labelFormatter={(l) => when(String(l))} formatter={(v) => [fmt(Number(v), cur), "Balance"]} />
                <Area type="stepAfter" dataKey="v" stroke={lineColor} strokeWidth={2} fill="url(#eqfill)" isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
            {curve.length <= 2 && <p className="muted chart-note">The curve fills in as trades close.</p>}
          </div>
        </section>

        <section className="panel acct-pnl" aria-label="Realised profit and loss">
          <h3>Realised P&L</h3>
          {p ? (
            <dl className="rows">
              <div><dt>Today <small>UTC day</small></dt><dd className={`num ${tone(p.today)}`}>{fmt(p.today, cur, true)}</dd></div>
              <div><dt>This week</dt><dd className={`num ${tone(p.week)}`}>{fmt(p.week, cur, true)}</dd></div>
              <div><dt>This month</dt><dd className={`num ${tone(p.month)}`}>{fmt(p.month, cur, true)}</dd></div>
              <div><dt>All time</dt><dd className={`num ${tone(p.all)}`}>{fmt(p.all, cur, true)}</dd></div>
              <div><dt>Win rate <small>{a.trades ?? 0} trades, {a.wins ?? 0} won</small></dt><dd className="num">{a.win_rate != null ? `${Math.round(a.win_rate * 100)}%` : "—"}</dd></div>
              <div><dt>Free margin {a.margin_level != null && <small>level {a.margin_level}%</small>}</dt><dd className="num">{fmt(a.free_margin, cur)}</dd></div>
            </dl>
          ) : <p className="muted">Trade history isn't available. Restart <code>mt5-gateway\start.ps1</code> to load it.</p>}
        </section>
      </div>

      <div className="two">
        <section className="panel">
          <h3>Open positions <span className="count">{a.positions.length}</span></h3>
          {a.positions.length === 0 ? <p className="muted">Nothing open. Positions appear here the moment they're filled.</p> : (
            <div className="tablewrap"><table className="tbl">
              <thead><tr><th>Symbol</th><th>Side</th><th>Lots</th><th>Entry</th><th>Stop</th><th>Target</th><th>P&L</th></tr></thead>
              <tbody>{a.positions.map((x) => (
                <tr key={x.id}><td><b>{x.symbol}</b></td><td><Side s={x.side} /></td>
                  <td className="num">{x.qty}</td><td className="num">{x.entry_price}</td><td className="num">{x.stop_loss ?? "—"}</td><td className="num">{x.take_profit ?? "—"}</td>
                  <td className={`num ${tone(x.unrealized_pnl)}`}><b>{fmt(x.unrealized_pnl, cur, true)}</b></td></tr>))}
              </tbody></table></div>
          )}
        </section>
        <section className="panel">
          <h3>Recently closed <span className="count">{a.recent?.length ?? 0}</span></h3>
          {!a.recent?.length ? <p className="muted">No closed trades yet.</p> : (
            <div className="tablewrap"><table className="tbl">
              <thead><tr><th>Closed</th><th>Symbol</th><th>Side</th><th>Lots</th><th>P&L</th></tr></thead>
              <tbody>{a.recent.map((t) => (
                <tr key={t.position_id}><td>{when(t.closed_at)}</td><td><b>{t.symbol}</b></td>
                  <td><Side s={t.side} /></td><td className="num">{t.volume}</td>
                  <td className={`num ${tone(t.pnl)}`}><b>{fmt(t.pnl, cur, true)}</b></td></tr>))}
              </tbody></table></div>
          )}
        </section>
      </div>
      <p className="foot muted">{at ? `Updated ${at.toLocaleTimeString()}` : ""}{err ? ". Last refresh failed, retrying." : ""}</p>
    </>
  );
}
