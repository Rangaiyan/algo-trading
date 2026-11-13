import { useCallback, useEffect, useState } from "react";
import { Download, RefreshCw } from "lucide-react";
import { type DataCatalog, getDataCatalog, startDownload } from "./api";

const TFS = ["M1", "M5", "M15", "H1", "H4", "D1"];
const day = (iso: string) => iso.slice(0, 10);
const ago = (iso: string) => {
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  return m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`;
};

/** Market Data: what real Deriv history is downloaded, its quality, and a button to download / top it up. */
export default function DataPage() {
  const [c, setC] = useState<DataCatalog | null>(null);
  const [err, setErr] = useState("");

  const load = useCallback(() => getDataCatalog().then((x) => { setC(x); setErr(""); }).catch((e) => setErr(e.message)), []);
  useEffect(() => {
    load();
    const id = setInterval(load, c?.job.running ? 2000 : 15000);
    return () => clearInterval(id);
  }, [load, c?.job.running]);

  async function download() {
    try { await startDownload(); load(); } catch (e) { setErr((e as Error).message); }
  }

  const symbols = [...new Set(c?.datasets.map((d) => d.symbol) ?? [])];
  const find = (s: string, tf: string) => c?.datasets.find((d) => d.symbol === s && d.timeframe === tf);
  const last = c?.datasets.map((d) => d.updated_at).sort().at(-1);
  const running = c?.job.running;

  return (
    <>
      <section className="desk-head">
        <div className="lbl" style={{ color: "var(--cyan)" }}>REAL HISTORY</div>
        <h2>Market Data</h2>
        <p className="muted">Candle history downloaded from your Deriv MT5 account, used by the Backtest Lab. Times are UTC and spreads are recorded per bar.
          The most recent 6 months of each set are held out as untouched test data.</p>
        <div className="data-actions">
          <button className="run" style={{ width: "auto" }} disabled={running} onClick={download}>
            {running ? <><RefreshCw size={14} className="spin" /> Downloading…</> : <><Download size={14} /> {c?.datasets.length ? "Update to latest" : "Download 5 years"}</>}
          </button>
          {last && <span className="muted">Last updated {ago(last)}</span>}
        </div>
      </section>

      {err && <div className="banner">{err}</div>}
      {c?.job.error && <div className="banner">Last download failed: {c.job.error}</div>}
      {(running || c?.log.length) ? (
        <div className="panel"><h3>{running ? "Download in progress" : "Last download"}</h3>
          <pre className="data-log">{c?.log.join("\n") || "Starting…"}</pre></div>
      ) : null}

      {!c ? <p className="muted">Loading…</p> : c.datasets.length === 0 ? (
        <div className="panel"><h3>No history downloaded yet</h3><p className="muted">Click “Download 5 years” with MT5 open and logged in. It takes a few minutes.</p></div>
      ) : (
        <div className="panel">
          <h3>Coverage <small className="muted">years of history per pair and timeframe</small></h3>
          <div className="tablewrap"><table className="tbl data-grid">
            <thead><tr><th>Pair</th>{TFS.map((tf) => <th key={tf}>{tf}</th>)}</tr></thead>
            <tbody>{symbols.map((s) => (
              <tr key={s}><td><b>{s}</b></td>{TFS.map((tf) => {
                const d = find(s, tf);
                if (!d) return <td key={tf} className="muted">—</td>;
                const enough = d.years >= 3;
                return (
                  <td key={tf} title={`${d.bars.toLocaleString()} bars · ${day(d.start)} → ${day(d.end)} · hold-out from ${day(d.holdout_start)} · version ${d.data_version}${d.quality.issues.length ? ` · ${d.quality.issues.join(", ")}` : ""}`}>
                    <span className={`cov ${enough ? "ok" : "short"}`}>{d.years}y</span>
                    <small className="muted"> {Math.round(d.bars / 1000)}k</small>
                    {!d.quality.ok && <small className="down"> ⚠</small>}
                  </td>
                );
              })}</tr>))}
            </tbody></table></div>
          <p className="muted small" style={{ marginTop: 10, lineHeight: 1.6 }}>
            Green = at least 3 years (the backtest minimum). M1/M5 are limited by MT5's <b>Max bars in chart</b> setting (100,000 per timeframe):
            set it to Unlimited in MT5 (Tools → Options → Charts), restart MT5, then press “Update to latest” to get more.
            Gold (XAUUSD) shows gaps at 22:00–23:00 UTC: that's its daily trading break, not missing data. Hover a cell for details.
          </p>
        </div>
      )}
    </>
  );
}
