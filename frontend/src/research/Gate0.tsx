import { useEffect, useState } from "react";
import { CheckCircle2, Scale, Upload, XCircle } from "lucide-react";
import { type Gate0Info, type Gate0Result, gate0Compare, gate0Info } from "../api";

const usd = (n: number) => `${n < 0 ? "-" : ""}$${Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;

/** Gate 0 (plan §2, §10.3 week 1): the Rinz engine must agree with MT5's own Strategy Tester before results count. */
export default function Gate0() {
  const [info, setInfo] = useState<Gate0Info | null>(null);
  const [res, setRes] = useState<Gate0Result | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => gate0Info().then(setInfo).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  async function run(csv?: string) {
    setBusy(true); setErr("");
    try { setRes(await gate0Compare(csv)); load(); }
    catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <>
      <section className="desk-head" style={{ ["--dc" as string]: "#f59e0b" }}>
        <div className="lbl" style={{ color: "#f59e0b" }}>GATE 0 · ENGINE VERIFICATION</div>
        <h2>Gate 0: Rinz vs MT5 Strategy Tester</h2>
        <p className="muted">Before any backtest result counts, the plan requires the Rinz engine to agree with an independent reference.
          MT5's Strategy Tester runs a simple reference strategy (EMA cross, fixed stop and target, fixed lots); Rinz runs the identical rules on the same data;
          the trades are matched one by one.</p>
      </section>

      <div className="two">
        <div className="panel howto">
          <h3>1 · Run the reference in MT5</h3>
          <ol>
            <li>In MetaTrader 5 press <b>Ctrl+R</b> (View → Strategy Tester).</li>
            <li><b>Expert:</b> <code>Rinz\RinzGate0</code> (already installed and compiled).</li>
            <li><b>Symbol:</b> EURUSD · <b>Timeframe:</b> H1 (or M15).</li>
            <li><b>Date:</b> Custom period, for example <b>2024.01.01 → 2025.12.31</b>. Keep it inside the history on the Market Data page.</li>
            <li><b>Modelling:</b> <i>1 minute OHLC</i> · <b>Deposit</b> 10000 USD · leverage as your account.</li>
            <li>Leave the inputs at their defaults (EMA 20/50, SL 30 pips, TP 60 pips, 0.10 lot), or change them: Rinz reads them from the result file.</li>
            <li>Press <b>Start</b> and wait for it to finish. The EA writes its trades to <code>Common\Files\rinz_gate0_trades.csv</code>.</li>
          </ol>
          <p className="muted small">The EA source is in <code>{info?.ea_source}</code>. Nothing is traded on your account: the tester is a simulation.</p>
        </div>
        <div className="panel">
          <h3>2 · Compare</h3>
          {info && (info.exists
            ? <p>Found the tester output: <b>{info.trades}</b> trades, written {info.modified?.slice(0, 16).replace("T", " ")} UTC.</p>
            : <p className="muted">No tester output yet. Run step 1 first.</p>)}
          <div className="builder-run">
            <button className="run" style={{ width: "auto" }} disabled={busy || !info?.exists} onClick={() => run()}><Scale size={14} /> {busy ? "Comparing…" : "Compare with Rinz"}</button>
            <label className="pill upload"><Upload size={13} /> Or upload a CSV
              <input type="file" accept=".csv,text/csv" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) f.text().then(run); }} /></label>
          </div>
          {info && <p className="muted small" style={{ marginTop: 10 }}>Pass requires: {Math.round((info.tolerances.match_rate ?? 0) * 100)}% of trades matched, trade count within
            {" "}{Math.round((info.tolerances.count_diff ?? 0) * 100)}%, median entry difference ≤ {info.tolerances.median_entry_pips} pip, net P&L within
            {" "}{Math.round((info.tolerances.net_diff ?? 0) * 100)}% and profit factor within {info.tolerances.pf_diff}.</p>}
          {err && <p className="err" role="alert">{err}</p>}
        </div>
      </div>

      {res && (
        <>
          <div className="panel opt-head">
            <div>
              <span className={`verdict ${res.verdict}`}>{res.verdict === "pass" ? "GATE 0 PASSED" : "GATE 0 NOT PASSED"}</span>
              <h3 style={{ margin: "8px 0 4px" }}>{res.symbol} {res.timeframe} · EMA {res.params.fast}/{res.params.slow} · SL {res.params.sl_pips} / TP {res.params.tp_pips} pips · {res.lots} lot</h3>
              <div className="muted small">{res.period[0].slice(0, 10)} → {res.period[1].slice(0, 10)} · MT5 {res.summary.ea_trades} trades vs Rinz {res.summary.our_trades} ·
                exit reasons agree {Math.round(res.summary.exit_reason_agreement * 100)}% · same-candle exits {res.summary.same_bar_exit_share == null ? "—" : `${Math.round(res.summary.same_bar_exit_share * 100)}%`}</div>
            </div>
          </div>
          <div className="panel">
            <table className="tbl gate"><thead><tr><th>Check</th><th>Result</th><th>Value</th><th>Required</th></tr></thead>
              <tbody>{res.checks.map((c) => <tr key={c.check} className={c.ok ? "pass" : "fail"}><td>{c.check}</td>
                <td className="gate-st">{c.ok ? <CheckCircle2 size={15} /> : <XCircle size={15} />} {c.ok ? "pass" : "fail"}</td><td>{c.value}</td><td className="muted">{c.required}</td></tr>)}</tbody></table>
            <ul className="muted small" style={{ marginTop: 10, lineHeight: 1.7 }}>{res.notes.map((n) => <li key={n}>{n}</li>)}</ul>
          </div>
          <div className="two">
            <div className="panel"><h3>Largest P&L differences <small className="muted">matched trades</small></h3>
              <div className="tablewrap"><table className="tbl"><thead><tr><th>Opened</th><th>Side</th><th>Entry Δ</th><th>Exit Δ</th><th>Exit MT5 / Rinz</th><th>MT5</th><th>Rinz</th></tr></thead>
                <tbody>{res.largest_differences.map((d, i) => <tr key={i}><td>{d.open_time.slice(0, 16).replace("T", " ")}</td><td>{d.side}</td>
                  <td>{d.entry_diff_pips}</td><td>{d.exit_diff_pips}</td><td>{d.ea_reason} / {d.our_reason}</td><td>{usd(d.ea_pnl)}</td><td>{usd(d.our_pnl)}</td></tr>)}</tbody></table></div></div>
            <div className="panel"><h3>Unmatched trades</h3>
              <p className="small"><b>Only in MT5 ({res.unmatched_mt5.length}):</b> {res.unmatched_mt5.slice(0, 8).map((t) => `${t.open_time.slice(0, 16).replace("T", " ")} ${t.side}`).join(" · ") || "none"}</p>
              <p className="small"><b>Only in Rinz ({res.unmatched_rinz.length}):</b> {res.unmatched_rinz.slice(0, 8).map((t) => `${t.open_time.slice(0, 16).replace("T", " ")} ${t.side}`).join(" · ") || "none"}</p>
              <p className="muted small">A few unmatched trades usually come from a candle where both the stop and the target were in reach, or from the first EMA values; a large number means the engines disagree.</p></div>
          </div>
        </>
      )}
    </>
  );
}
