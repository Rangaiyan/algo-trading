import { useEffect, useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getDeskTrades, type DeskData } from "../api";
import { DESK_COLORS } from "../nav";
import { useChartColors } from "../theme";
import "../dashboard.css";
import "./desk.css";

const DESK_INFO: Record<string, { title: string; eyebrow: string; blurb: string }> = {
  ema: { title: "EMA Desk", eyebrow: "Trend following", blurb: "EMA trend rules. EMA-1 buys pullbacks to the 20/50 EMA inside an EMA-200 trend; EMA-2 trades a fast/slow crossover filtered by ADX." },
  candle: { title: "Candle Desk", eyebrow: "Candlestick patterns", blurb: "Engulfing and pin-bar patterns in the direction of the EMA-200 trend, stop beyond the pattern, fixed reward-to-risk." },
  ict: { title: "ICT Desk", eyebrow: "Time and price", blurb: "Kill-zone liquidity raids, optimal trade entry, Silver Bullet windows and the New York open. No strategies yet (Phase 2)." },
  smc: { title: "SMC Desk", eyebrow: "Market structure", blurb: "Liquidity sweep + CHoCH + order block / FVG entries, BOS continuation and FVG mitigation. No strategies yet (Phase 2)." },
  manual: { title: "Manual Trades", eyebrow: "Placed by you", blurb: "Trades you placed yourself in the MT5 terminal (magic number 0)." },
};

const fmt = (n: number, cur = "USD", plus = false) => {
  const s = Math.abs(n).toLocaleString(undefined, { style: "currency", currency: cur, minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${n < 0 ? "-" : plus && n > 0 ? "+" : ""}${s}`;
};
const tone = (n: number) => (n > 0 ? "up" : n < 0 ? "down" : "");
const pnlCls = (n: number) => (n > 0 ? "pos" : n < 0 ? "neg" : "");
const pct = (x: number | null) => (x == null ? "—" : `${Math.round(x * 100)}%`);
const when = (iso: string) => new Date(iso).toLocaleString(undefined, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
const Side = ({ s }: { s: "buy" | "sell" }) => <span className={`side-badge ${s}`}>{s === "buy" ? "Long" : "Short"}</span>;

function Stat({ label, value, sub, cls = "" }: { label: string; value: React.ReactNode; sub?: React.ReactNode; cls?: string }) {
  return <div className={`tile ${cls}`}><div className="lbl">{label}</div><div className={`v ${cls === "pos" ? "up" : cls === "neg" ? "down" : ""}`}>{value}</div>{sub && <div className="s">{sub}</div>}</div>;
}

/** A strategy desk: real MT5 trades whose magic number belongs to this desk. Refreshes every 15 s. */
export default function DeskPage({ desk }: { desk: string }) {
  const info = DESK_INFO[desk];
  const color = DESK_COLORS[desk as keyof typeof DESK_COLORS] ?? "var(--text)";
  const cc = useChartColors();
  const [d, setD] = useState<DeskData | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let dead = false;
    setD(null);
    const load = async () => {
      try { const x = await getDeskTrades(desk); if (!dead) { setD(x); setErr(""); } }
      catch (e) { if (!dead) setErr((e as Error).message); }
    };
    load();
    const id = setInterval(load, 15000);
    return () => { dead = true; clearInterval(id); };
  }, [desk]);

  const head = (
    <section className="desk-head" style={{ ["--dc" as string]: color }}>
      <div className="lbl" style={{ color }}>{info.eyebrow}</div>
      <h2>{info.title}</h2>
      <p className="muted">{info.blurb}</p>
      {d?.connected && <span className="chip">MT5 magic {d.magic_range[0] === d.magic_range[1] ? d.magic_range[0] : `${d.magic_range[0]}–${d.magic_range[1]}`}</span>}
    </section>
  );

  if (err && !d) return <>{head}<div className="panel"><p className="err">{err}. Is the backend running on port 8000?</p></div></>;
  if (!d) return <>{head}<p className="muted">Loading this desk's trades…</p></>;
  if (!d.connected) return <>{head}<div className="panel"><h3>MT5 account not connected</h3><p className="muted">{d.detail}</p></div></>;

  const cur = d.currency;
  const empty = d.trades === 0 && d.positions.length === 0;

  return (
    <>
      {head}
      {!d.history_available && <div className="banner">Trade history isn't available from the MT5 gateway. Restart mt5-gateway/start.ps1 to load it.</div>}

      <div className="grid5">
        <Stat label="Net P&L" value={fmt(d.net, cur, true)} cls={pnlCls(d.net)} sub="realised, after costs" />
        <Stat label="Floating" value={fmt(d.floating, cur, true)} cls={pnlCls(d.floating)} sub={`${d.positions.length} open`} />
        <Stat label="Trades" value={d.trades} sub={`${d.wins}W / ${d.losses}L`} />
        <Stat label="Win rate" value={pct(d.win_rate)} />
        <Stat label="Profit factor" value={d.profit_factor ?? "—"} sub={`avg win ${d.avg_win != null ? fmt(d.avg_win, cur) : "—"} · avg loss ${d.avg_loss != null ? fmt(d.avg_loss, cur) : "—"}`} />
        <Stat label="Best / worst" value={<><span className="up">{d.best != null ? fmt(d.best, cur, true) : "—"}</span> <span className="muted">/</span> <span className="down">{d.worst != null ? fmt(d.worst, cur, true) : "—"}</span></>} />
      </div>

      {empty && (
        <div className="note">
          {desk === "manual"
            ? "No manual trades yet. Anything you open by hand in the MT5 terminal appears here."
            : "No real trades from this desk yet. Once its strategies place orders on MT5 (Phase 5), each order carries its magic number and lands here automatically."}
        </div>
      )}

      {desk !== "manual" && (
        <div className="panel">
          <h3>Strategies</h3>
          {d.strategies.length === 0 ? <p className="muted">No strategies registered for this desk yet.</p> : (
            <table className="tbl">
              <thead><tr><th>Strategy</th><th>Magic</th><th>Trades</th><th>Win rate</th><th>Net P&L</th></tr></thead>
              <tbody>{d.strategies.map((s) => (
                <tr key={s.strategy}><td><b>{s.strategy}</b></td><td>{s.magic}</td><td>{s.trades}</td><td>{pct(s.win_rate)}</td>
                  <td className={tone(s.net)}><b>{fmt(s.net, cur, true)}</b></td></tr>))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {d.curve.length >= 2 && (
        <div className="panel">
          <h3>Cumulative P&L</h3>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={d.curve}>
              <CartesianGrid stroke={cc.grid} />
              <XAxis dataKey="t" tickFormatter={(t) => String(t).slice(5, 10)} minTickGap={40} stroke={cc.axis} />
              <YAxis stroke={cc.axis} width={60} />
              <Tooltip contentStyle={{ background: cc.tipBg, border: `1px solid ${cc.tipBorder}`, color: cc.tipText }}
                labelFormatter={(l) => when(String(l))} formatter={(v) => fmt(Number(v), cur, true)} />
              <Area type="stepAfter" dataKey="cum" name="P&L" stroke={d.net >= 0 ? cc.up : cc.down} fill={(d.net >= 0 ? cc.up : cc.down) + "26"} strokeWidth={2} isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {d.positions.length > 0 && (
        <div className="panel">
          <h3>Open positions</h3>
          <div className="tablewrap"><table className="tbl">
            <thead><tr><th>Opened</th><th>Strategy</th><th>Symbol</th><th>Side</th><th>Lots</th><th>Entry</th><th>SL</th><th>TP</th><th>P&L</th></tr></thead>
            <tbody>{d.positions.map((x) => (
              <tr key={x.id}><td>{when(x.opened_at)}</td><td>{x.strategy}</td><td><b>{x.symbol}</b></td><td><Side s={x.side} /></td><td>{x.qty}</td>
                <td>{x.entry_price}</td><td>{x.stop_loss ?? "—"}</td><td>{x.take_profit ?? "—"}</td>
                <td className={tone(x.unrealized_pnl)}><b>{fmt(x.unrealized_pnl, cur, true)}</b></td></tr>))}
            </tbody></table></div>
        </div>
      )}

      {d.closed.length > 0 && (
        <div className="panel">
          <h3>Closed trades</h3>
          <div className="tablewrap"><table className="tbl">
            <thead><tr><th>Closed</th><th>Strategy</th><th>Symbol</th><th>Side</th><th>Lots</th><th>Entry</th><th>Exit</th><th>P&L</th></tr></thead>
            <tbody>{d.closed.map((t) => (
              <tr key={t.position_id}><td>{when(t.closed_at)}</td><td>{t.strategy}</td><td><b>{t.symbol}</b></td><td><Side s={t.side} /></td><td>{t.volume}</td>
                <td>{t.entry_price}</td><td>{t.exit_price}</td><td className={tone(t.pnl)}><b>{fmt(t.pnl, cur, true)}</b></td></tr>))}
            </tbody></table></div>
        </div>
      )}
    </>
  );
}
