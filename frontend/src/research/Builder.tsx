import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Play, Save, Sliders } from "lucide-react";
import { type BacktestResult, type BuilderInfo, type RuleBlock, type RuleSpec, builderInfo, runBacktest, saveToLibrary, validateSpec } from "../api";
import { money, pf, tone } from "./format";

const SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD"];
const TFS = ["M15", "H1", "H4"];
const LABEL: Record<string, string> = {
  structure_break: "Structure break (trigger)", liquidity_sweep: "Liquidity sweep", htf_bias: "H4 bias agrees",
  premium_discount: "Premium / discount", ema_trend: "EMA trend", candle_confirm: "Candle confirmation", session: "Inside session",
};
const DEFAULT_BLOCK: Record<string, RuleBlock> = {
  structure_break: { block: "structure_break", kind: "any", displacement: true, weight: 2 },
  liquidity_sweep: { block: "liquidity_sweep", levels: ["prev_day_hl", "asia_hl", "equal_hl"], within: 30, weight: 2 },
  htf_bias: { block: "htf_bias", weight: 2 }, premium_discount: { block: "premium_discount", weight: 1 },
  ema_trend: { block: "ema_trend", fast: 50, slow: 200, weight: 1 },
  candle_confirm: { block: "candle_confirm", patterns: ["engulfing", "pin_bar"], weight: 1 },
  session: { block: "session", sessions: ["london_kz", "ny_am_kz"], weight: 1 },
};

function Multi({ all, value, onChange }: { all: string[]; value: string[]; onChange: (v: string[]) => void }) {
  return <span className="multi">{all.map((x) => (
    <button key={x} type="button" className={`chip x ${value.includes(x) ? "on" : ""}`} aria-pressed={value.includes(x)}
      onClick={() => onChange(value.includes(x) ? value.filter((y) => y !== x) : [...value, x])}>{x}</button>))}</span>;
}

/** Rule Builder (doc 9.2 + 9.1): assemble a strategy from building blocks, with all-must-pass or confluence scoring. */
export default function Builder() {
  const nav = useNavigate();
  const incoming = (useLocation() as { state?: { spec?: RuleSpec; symbol?: string; timeframe?: string } }).state;
  const [info, setInfo] = useState<BuilderInfo | null>(null);
  const [spec, setSpec] = useState<RuleSpec | null>(null);
  const [json, setJson] = useState<string | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [where, setWhere] = useState({ symbol: incoming?.symbol ?? "EURUSD", timeframe: incoming?.timeframe ?? "H1" });
  const [res, setRes] = useState<BacktestResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => { builderInfo().then((i) => { setInfo(i); setSpec(incoming?.spec ?? i.example); }).catch((e) => setMsg(e.message)); }, [incoming]);
  useEffect(() => {
    if (!spec) return;
    const t = setTimeout(() => validateSpec(spec).then((r) => setErrors(r.errors)).catch(() => {}), 250);
    return () => clearTimeout(t);
  }, [spec]);

  const totalWeight = useMemo(() => (spec?.setup ?? []).reduce((a, b) => a + (b.weight ?? 1), 0), [spec]);
  if (!info || !spec) return <p className="muted">{msg || "Loading…"}</p>;

  const up = (f: (s: RuleSpec) => RuleSpec) => { setSpec((s) => (s ? f(structuredClone(s)) : s)); setRes(null); };
  const has = (b: string) => spec.setup.some((x) => x.block === b);
  const block = (b: string) => spec.setup.find((x) => x.block === b)!;
  const setBlock = (b: string, patch: Partial<RuleBlock>) => up((s) => ({ ...s, setup: s.setup.map((x) => (x.block === b ? { ...x, ...patch } : x)) }));
  const toggle = (b: string) => up((s) => ({ ...s, setup: has(b) ? s.setup.filter((x) => x.block !== b) : [...s.setup, structuredClone(DEFAULT_BLOCK[b])] }));

  async function test() {
    setBusy(true); setMsg("");
    try { setRes(await runBacktest({ strategy: "RULE", symbol: where.symbol, timeframe: where.timeframe, source: "store", days: 0, risk_pct: 0.5, cost_stress: 1, commission_per_lot: 0, include_holdout: false, params: { spec } })); }
    catch (e) { setMsg((e as Error).message); }
    finally { setBusy(false); }
  }

  async function save() {
    try {
      const e = await saveToLibrary({ name: spec?.name, strategy: "RULE", symbol: where.symbol, timeframe: where.timeframe, params: { spec } });
      setMsg(`Saved as a draft: ${e.id}. Validate it in the Optimiser before it can be promoted.`);
    } catch (e) { setMsg((e as Error).message); }
  }

  const ex = spec.exit ?? {}, en = spec.entry ?? {}, tp = ex.take_profit ?? {};
  return (
    <>
      <section className="desk-head" style={{ ["--dc" as string]: "#ec4899" }}>
        <div className="lbl" style={{ color: "#ec4899" }}>NO-CODE RULES</div>
        <h2>Rule Builder</h2>
        <p className="muted">Build a strategy from the structure library's blocks. Every setup starts at a BOS/CHoCH on a closed candle; the other blocks decide whether to take it,
          either <b>all must pass</b> or as a <b>confluence score</b> (plan §9.1: weights add up, trade when the total reaches the threshold).</p>
      </section>

      <div className="opt-grid">
        <section className="panel form">
          <label>Name<input value={spec.name ?? ""} onChange={(e) => up((s) => ({ ...s, name: e.target.value }))} /></label>
          <label>Decision
            <select value={spec.mode ?? "all"} onChange={(e) => up((s) => ({ ...s, mode: e.target.value as "all" | "score", threshold: s.threshold ?? 6 }))}>
              <option value="all">All blocks must pass</option><option value="score">Confluence score</option>
            </select>
          </label>
          {spec.mode === "score" && (
            <label>Threshold: {spec.threshold} of {totalWeight}
              <input type="range" min={1} max={Math.max(1, totalWeight)} value={spec.threshold ?? 6} onChange={(e) => up((s) => ({ ...s, threshold: +e.target.value }))} />
            </label>
          )}
          <h4 className="lib-h">Always required (filters)</h4>
          <div className="small muted">Sessions (New York time); none = any time</div>
          <Multi all={Object.keys(info.sessions)} value={spec.filters?.sessions ?? []} onChange={(v) => up((s) => ({ ...s, filters: { ...s.filters, sessions: v } }))} />
          <label style={{ marginTop: 10 }}>Max spread (pips, 0 = off)
            <input type="number" step={0.1} min={0} value={spec.filters?.max_spread_pips ?? 0} onChange={(e) => up((s) => ({ ...s, filters: { ...s.filters, max_spread_pips: +e.target.value || undefined } }))} />
          </label>
          <h4 className="lib-h">Structure settings</h4>
          <div className="row3">
            <label>Swing size<input type="number" min={1} max={10} value={spec.structure?.swing_n ?? 3} onChange={(e) => up((s) => ({ ...s, structure: { ...s.structure, swing_n: +e.target.value } }))} /></label>
            <label>Displacement ×ATR<input type="number" step={0.25} min={0.5} max={5} value={spec.structure?.displacement_k ?? 1.5} onChange={(e) => up((s) => ({ ...s, structure: { ...s.structure, displacement_k: +e.target.value } }))} /></label>
            <label>Min FVG ×ATR<input type="number" step={0.1} min={0} max={3} value={spec.structure?.fvg_min_atr ?? 0.3} onChange={(e) => up((s) => ({ ...s, structure: { ...s.structure, fvg_min_atr: +e.target.value } }))} /></label>
          </div>
        </section>

        <section>
          <div className="panel">
            <h3>Setup blocks</h3>
            <div className="blocks">
              {Object.keys(info.blocks).map((b) => {
                const on = has(b), x = on ? block(b) : null;
                return (
                  <div key={b} className={`blk ${on ? "on" : ""}`}>
                    <label className="blk-head">
                      <input type="checkbox" checked={on} onChange={() => toggle(b)} />
                      <b>{LABEL[b] ?? b}</b>
                      {on && spec.mode === "score" && <span className="blk-w">weight <input type="number" min={0} max={5} value={x!.weight ?? 1} onChange={(e) => setBlock(b, { weight: +e.target.value })} aria-label={`${b} weight`} /></span>}
                    </label>
                    <div className="muted small">{info.blocks[b]}</div>
                    {on && b === "structure_break" && (
                      <div className="blk-opts">
                        <select value={String(x!.kind ?? "any")} onChange={(e) => setBlock(b, { kind: e.target.value })} aria-label="break kind"><option value="any">BOS or CHoCH</option><option value="BOS">BOS (continuation)</option><option value="CHoCH">CHoCH (reversal)</option></select>
                        <label className="check"><input type="checkbox" checked={!!x!.displacement} onChange={(e) => setBlock(b, { displacement: e.target.checked })} /> needs displacement</label>
                      </div>)}
                    {on && b === "liquidity_sweep" && (
                      <div className="blk-opts"><Multi all={info.levels} value={(x!.levels as string[]) ?? []} onChange={(v) => setBlock(b, { levels: v })} />
                        <label>within <input type="number" min={1} max={200} value={Number(x!.within ?? 30)} onChange={(e) => setBlock(b, { within: +e.target.value })} /> bars</label></div>)}
                    {on && b === "ema_trend" && (
                      <div className="blk-opts"><label>fast <input type="number" min={2} max={200} value={Number(x!.fast ?? 50)} onChange={(e) => setBlock(b, { fast: +e.target.value })} /></label>
                        <label>slow <input type="number" min={5} max={400} value={Number(x!.slow ?? 200)} onChange={(e) => setBlock(b, { slow: +e.target.value })} /></label></div>)}
                    {on && b === "candle_confirm" && <div className="blk-opts"><Multi all={info.patterns} value={(x!.patterns as string[]) ?? []} onChange={(v) => setBlock(b, { patterns: v })} /></div>}
                    {on && b === "session" && <div className="blk-opts"><Multi all={Object.keys(info.sessions)} value={(x!.sessions as string[]) ?? []} onChange={(v) => setBlock(b, { sessions: v })} /></div>}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="two">
            <div className="panel form">
              <h3>Entry</h3>
              <label>Order<select value={en.type ?? "zone"} onChange={(e) => up((s) => ({ ...s, entry: { ...s.entry, type: e.target.value as "zone" | "market" } }))}>
                <option value="zone">Limit order at a zone (OB / FVG)</option><option value="market">Market order on the next candle</option></select></label>
              {(en.type ?? "zone") === "zone" && <>
                <div className="small muted">Zone types, first one preferred</div>
                <Multi all={["ob", "fvg"]} value={en.zone ?? ["ob", "fvg"]} onChange={(v) => up((s) => ({ ...s, entry: { ...s.entry, zone: v } }))} />
                <label style={{ marginTop: 8 }}>Price<select value={en.at ?? "edge"} onChange={(e) => up((s) => ({ ...s, entry: { ...s.entry, at: e.target.value as "edge" | "mid" } }))}>
                  <option value="edge">Zone edge</option><option value="mid">Zone 50%</option></select></label>
                <label>Cancel after (bars)<input type="number" min={1} max={200} value={en.expires_bars ?? 20} onChange={(e) => up((s) => ({ ...s, entry: { ...s.entry, expires_bars: +e.target.value } }))} /></label>
              </>}
            </div>
            <div className="panel form">
              <h3>Exit</h3>
              <label>Stop-loss<select value={ex.stop ?? "zone"} onChange={(e) => up((s) => ({ ...s, exit: { ...s.exit, stop: e.target.value as "sweep" | "zone" | "atr" } }))}>
                <option value="sweep">Beyond the sweep extreme</option><option value="zone">Beyond the zone</option><option value="atr">ATR distance</option></select></label>
              <label>Buffer ×ATR<input type="number" step={0.05} min={0} max={2} value={ex.buffer_atr ?? 0.2} onChange={(e) => up((s) => ({ ...s, exit: { ...s.exit, buffer_atr: +e.target.value } }))} /></label>
              <label>Take-profit<select value={tp.type ?? "rr"} onChange={(e) => up((s) => ({ ...s, exit: { ...s.exit, take_profit: { ...tp, type: e.target.value as "rr" | "next_liquidity" } } }))}>
                <option value="rr">Fixed reward-to-risk</option><option value="next_liquidity">Next liquidity pool (min RR)</option></select></label>
              <label>{(tp.type ?? "rr") === "rr" ? "RR" : "Minimum RR"}
                <input type="number" step={0.25} min={0.5} max={10} value={(tp.type ?? "rr") === "rr" ? tp.rr ?? 2 : tp.min_rr ?? 2}
                  onChange={(e) => up((s) => ({ ...s, exit: { ...s.exit, take_profit: { ...tp, [(tp.type ?? "rr") === "rr" ? "rr" : "min_rr"]: +e.target.value } } }))} /></label>
            </div>
          </div>

          {errors.length > 0 && <div className="banner">{errors.join(" · ")}</div>}
          <div className="panel builder-run">
            <select value={where.symbol} onChange={(e) => setWhere((w) => ({ ...w, symbol: e.target.value }))} aria-label="pair">{SYMBOLS.map((s) => <option key={s}>{s}</option>)}</select>
            <select value={where.timeframe} onChange={(e) => setWhere((w) => ({ ...w, timeframe: e.target.value }))} aria-label="timeframe">{TFS.map((s) => <option key={s}>{s}</option>)}</select>
            <button className="run" disabled={busy || errors.length > 0} onClick={test}><Play size={14} /> {busy ? "Testing…" : "Quick backtest"}</button>
            <button className="run alt" disabled={errors.length > 0} onClick={() => nav("/optimizer", { state: { strategy: "RULE", base: { spec }, ...where } })}><Sliders size={14} /> Optimise &amp; validate</button>
            <button className="run alt" disabled={errors.length > 0} onClick={save}><Save size={14} /> Save draft</button>
          </div>
          {msg && <div className="note">{msg}</div>}
          {res && (
            <div className="cards">
              {[
                ["Trades", String(res.metrics.trades), ""], ["Net", money(res.metrics.net_profit), tone(res.metrics.net_profit)],
                ["Profit factor", pf(res.metrics.profit_factor), (res.metrics.profit_factor ?? 0) >= 1.3 ? "up" : (res.metrics.profit_factor ?? 0) < 1 ? "down" : ""],
                ["Win rate", `${Math.round(res.metrics.win_rate * 100)}%`, ""], ["Max DD", `${res.metrics.max_drawdown_pct}%`, ""],
              ].map(([l, v, t]) => <div key={l} className="card"><div className="muted">{l}</div><div className={`big ${t}`}>{v}</div></div>)}
            </div>
          )}
          {res && <p className="muted small">{res.symbol} {res.timeframe} · {res.range[0].slice(0, 10)} → {res.range[1].slice(0, 10)} (hold-out excluded). Open Backtest Lab for the chart of a built-in strategy.</p>}

          <details className="panel">
            <summary>JSON</summary>
            <textarea className="json" spellCheck={false} value={json ?? JSON.stringify(spec, null, 2)} onChange={(e) => setJson(e.target.value)} aria-label="Rule JSON" />
            <div className="builder-run">
              <button className="pill" disabled={json === null} onClick={() => { try { setSpec(JSON.parse(json!)); setJson(null); setMsg(""); } catch (e) { setMsg(`JSON error: ${(e as Error).message}`); } }}>Apply JSON</button>
              <button className="pill" onClick={() => { setSpec(info.example); setJson(null); }}>Reset to example</button>
            </div>
          </details>
        </section>
      </div>
    </>
  );
}
