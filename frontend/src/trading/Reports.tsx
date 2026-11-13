import { useEffect, useState } from "react";
import { Download, FileText } from "lucide-react";
import { type ReportSummary, reportSummary, reportUrl } from "../api";

const PERIODS = ["daily", "weekly", "monthly", "all"] as const;
const usd = (n: number | null | undefined) => (n == null ? "—" : `${n < 0 ? "-" : n > 0 ? "+" : ""}$${Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 2 })}`);

/** Reports (doc 16): period summary, trade history CSV, printable performance report (Print -> Save as PDF). */
export default function Reports() {
  const [period, setPeriod] = useState<(typeof PERIODS)[number]>("weekly");
  const [s, setS] = useState<ReportSummary | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    let dead = false;
    reportSummary(period).then((x) => { if (!dead) { setS(x); setErr(""); } }).catch((e) => { if (!dead) setErr(e.message); });
    return () => { dead = true; };
  }, [period]);

  return (
    <>
      <section className="desk-head" style={{ ["--dc" as string]: "#4f8cff" }}>
        <div className="lbl" style={{ color: "#4f8cff" }}>REPORTS</div>
        <h2>Reports</h2>
        <p className="muted">From the broker's closed deals, net of all costs. The daily summary is also sent to Telegram after the 17:00 New York close
          (once Telegram is set up), and <code>/report daily|weekly|monthly</code> works in the bot.</p>
      </section>
      <div className="panel report-bar">
        <div className="seg" role="tablist">{PERIODS.map((p) => <button key={p} className={p === period ? "on" : ""} onClick={() => setPeriod(p)} aria-pressed={p === period}>{p}</button>)}</div>
        <span className="sh-spacer" />
        <a className="pill" href={reportUrl("trades.csv", period)} download><Download size={13} /> Trade history (CSV)</a>
        <a className="pill" href={reportUrl("performance.html", period)} target="_blank" rel="noreferrer"><FileText size={13} /> Performance report (print → PDF)</a>
      </div>
      {err && <div className="banner">{err}</div>}
      {s && (
        <>
          <div className="grid5">
            <div className="tile"><div className="lbl">Trades</div><div className="v">{s.trades}</div><div className="s">{s.wins} won · {s.losses} lost</div></div>
            <div className="tile"><div className="lbl">Net P&L</div><div className={`v ${s.net_pnl >= 0 ? "up" : "down"}`}>{usd(s.net_pnl)}</div></div>
            <div className="tile"><div className="lbl">Win rate</div><div className="v">{s.win_rate == null ? "—" : `${Math.round(s.win_rate * 100)}%`}</div></div>
            <div className="tile"><div className="lbl">Profit factor</div><div className="v">{s.profit_factor ?? "—"}</div></div>
            <div className="tile"><div className="lbl">Best / worst</div><div className="v small-v">{usd(s.best)} / {usd(s.worst)}</div></div>
          </div>
          <div className="two">
            <div className="panel"><h3>By strategy</h3>
              <table className="tbl"><thead><tr><th>Strategy</th><th>Trades</th><th>Won</th><th>P&L</th></tr></thead>
                <tbody>{s.by_strategy.map((e) => <tr key={e.strategy}><td>{e.strategy}</td><td>{e.trades}</td><td>{e.wins}</td><td className={e.pnl >= 0 ? "up" : "down"}>{usd(e.pnl)}</td></tr>)}</tbody></table>
              {s.by_strategy.length === 0 && <p className="muted">No closed trades in this period.</p>}</div>
            <div className="panel"><h3>Telegram text</h3><pre className="data-log">{s.text}</pre>
              <p className="muted small">{s.disclaimer}</p></div>
          </div>
        </>
      )}
    </>
  );
}
