import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { getTrade, type TradeRow } from "../api";
import { dt, held, money, pips, price, reasonLabel, tone } from "./format";

function Tile({ label, value, sub, cls = "" }: { label: string; value: React.ReactNode; sub?: string; cls?: string }) {
  return <div className="mtile"><div className="lbl">{label}</div><div className={`mv ${cls}`}>{value}</div>{sub && <div className="s">{sub}</div>}</div>;
}

function Timeline({ t }: { t: TradeRow }) {
  const pts = [
    { k: "worst", label: "worst", p: t.worst_price, c: "var(--red)" },
    { k: "in", label: "in", p: t.entry_px, c: "var(--violet)" },
    { k: "out", label: "out", p: t.exit_px, c: t.pnl >= 0 ? "var(--green)" : "var(--red)" },
    { k: "best", label: "best", p: t.best_price, c: "var(--green)" },
    ...(t.stop_loss ? [{ k: "sl", label: "stop", p: t.stop_loss, c: "#ff8f8f" }] : []),
    ...(t.take_profit ? [{ k: "tp", label: "target", p: t.take_profit, c: "#8fe3a8" }] : []),
  ];
  const mn = Math.min(...pts.map((x) => x.p)), sp = Math.max(...pts.map((x) => x.p)) - mn || 1;
  // Labels of nearby points would overlap: walk left to right and rotate them through 4 vertical slots.
  const placed = pts.map((x) => ({ ...x, left: 4 + ((x.p - mn) / sp) * 92 })).sort((a, b) => a.left - b.left);
  let slot = 0;
  placed.forEach((x, i) => { slot = i > 0 && x.left - placed[i - 1].left < 14 ? (slot + 1) % 4 : 0; (x as { slot?: number }).slot = slot; });
  return (
    <div className="timeline" aria-label="Trade price timeline">
      <div className="tl-line" />
      {placed.map((x) => (
        <div key={x.k} className="tl-pt" style={{ left: `${x.left}%` }}>
          <i style={{ background: x.c }} /><span className={`s${(x as { slot?: number }).slot}`} style={{ color: x.c }}>{x.label} {price(t.symbol, x.p)}</span>
        </div>
      ))}
    </div>
  );
}

export default function TradeModal({ tradeId, onClose, onLocate }: { tradeId: number; onClose: () => void; onLocate?: (t: TradeRow) => void }) {
  const [d, setD] = useState<{ trade: TradeRow; session: { id: string; name: string } } | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { getTrade(tradeId).then(setD).catch((e) => setErr(e.message)); }, [tradeId]);
  useEffect(() => { const h = (e: KeyboardEvent) => e.key === "Escape" && onClose(); window.addEventListener("keydown", h); return () => window.removeEventListener("keydown", h); }, [onClose]);

  const t = d?.trade;
  const cost = (n: number) => (n === 0 ? money(0) : `-${money(n)}`);
  const travel = t ? Math.max(t.mfe_pips, t.mae_pips, Math.abs(t.pips), 1) : 1;
  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Trade detail" onClick={(e) => e.stopPropagation()}>
        {!t ? <div className="modal-body">{err ? <p className="err">{err}</p> : <p className="muted">Loading trade…</p>}<button className="pill" onClick={onClose}>Close</button></div> : (
          <>
            <header className="modal-head">
              <span className={`side-badge ${t.side}`}>{t.side === "buy" ? "LONG" : "SHORT"}</span>
              <b style={{ fontSize: 16 }}>{t.symbol}</b>
              <span className="muted">{price(t.symbol, t.entry_px)} → {price(t.symbol, t.exit_px)}</span>
              <span className="muted">{dt(t.entry_ts)} → {dt(t.exit_ts)} UTC · {held(t.held_minutes)}</span>
              <span className="sh-spacer" />
              <b className={`big ${tone(t.pnl)}`}>{money(t.pnl, true)}</b>
              <button className="pill" onClick={onClose} aria-label="Close"><X size={12} /></button>
            </header>
            <div className="modal-body">
              <div className="mgrid4">
                <Tile label="Pips" value={pips(t.pips)} cls={tone(t.pips)} sub={`${t.qty} lots`} />
                <Tile label="Peak profit" value={money(t.peak_profit)} cls="up" sub={`best price ${price(t.symbol, t.best_price)}`} />
                <Tile label="Given back" value={money(t.given_back)} cls="amb" sub={`kept ${t.kept_pct}% of its best`} />
                <Tile label="Booked" value={money(t.pnl, true)} cls={tone(t.pnl)} sub={`after ${money(t.total_costs)} costs`} />
              </div>

              <div className="msec">How far it travelled (pips)</div>
              {([["Best (MFE)", t.mfe_pips, "var(--green)"], ["Worst (MAE)", -t.mae_pips, "var(--red)"], ["Result", t.pips, t.pips >= 0 ? "var(--green)" : "var(--red)"]] as const).map(([l, v, c]) => (
                <div key={l} className="travel"><span>{l}</span><div><i style={{ width: `${(Math.abs(v) / travel) * 100}%`, background: c }} /></div><b>{pips(v)}</b></div>
              ))}
              <p className="muted s">It reached {t.mfe_pips.toFixed(1)} pips in profit and {t.mae_pips.toFixed(1)} against you before closing at {pips(t.pips)}.{t.capture !== null ? ` Capture ${(t.capture * 100).toFixed(0)}% of the best move.` : ""}</p>
              <Timeline t={t} />

              <div className="msec">The risk plan</div>
              <div className="mgrid4">
                <Tile label="Stop" value={price(t.symbol, t.stop_loss)} sub={t.stop_pips !== null ? `${t.stop_pips} pips away` : ""} />
                <Tile label="Target" value={t.take_profit ? price(t.symbol, t.take_profit) : "—"} sub={t.target_pips !== null ? `${t.target_pips} pips · planned R:R 1:${t.planned_rr}` : ""} />
                <Tile label="Money at risk" value={money(t.risk_money)} sub="size × stop distance" />
                <Tile label="R multiple" value={`${t.r_multiple >= 0 ? "+" : ""}${t.r_multiple.toFixed(2)}R`} cls={tone(t.r_multiple)} sub={reasonLabel[t.exit_reason] ?? t.exit_reason} />
              </div>

              <div className="msec">What it cost</div>
              <div className="mgrid5">
                <Tile label="Gross move" value={money(t.gross_pnl, true)} sub="mid-price, no costs" />
                <Tile label="Spread" value={cost(t.spread_cost)} cls="down" />
                <Tile label="Slippage" value={cost(t.slippage_cost)} cls="down" />
                <Tile label="Commission" value={cost(t.commission)} cls="down" />
                <Tile label="Swap" value={t.swap === 0 ? money(0) : t.swap > 0 ? `-${money(t.swap)}` : `+${money(-t.swap)}`} cls={t.swap > 0 ? "down" : t.swap < 0 ? "up" : ""} sub={t.overnight ? "held over rollover" : "no rollover"} />
              </div>

              <div className="msec">The trade</div>
              <div className="mgrid4">
                <Tile label="Entered" value={dt(t.entry_ts).slice(4)} sub={`session: ${t.entry_session}`} />
                <Tile label="Exited" value={dt(t.exit_ts).slice(4)} sub={t.overnight ? "carried over 17:00 NY roll" : "same trading day"} />
                <Tile label="Held for" value={held(t.held_minutes)} sub={`${t.bars_held} candles`} />
                <Tile label="Size" value={`${t.qty} lots`} sub={t.strategy} />
              </div>
              <footer className="modal-foot">
                <span className="muted">ticket #{t.id} · {d?.session.name} · session {t.session_id} · times UTC · demo data</span>
                {onLocate && <button className="pill" onClick={() => { onLocate(t); onClose(); }}>SHOW ON CHART</button>}
              </footer>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
