import { useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries, ColorType, CrosshairMode, createChart, createSeriesMarkers,
  type IChartApi, type ISeriesApi, type SeriesMarker, type Time, type UTCTimestamp,
} from "lightweight-charts";
import { RefreshCw } from "lucide-react";
import { API } from "../api";
import { useChartColors } from "../theme";
import { type Box, type OverlayData, type Seg, StructureOverlay } from "./StructureOverlay";

type Zone = { kind: "OB" | "BREAKER" | "FVG"; dir: number; top: number; bottom: number; from: number; to: number; mitigated: number | null; state: string };
type Resp = {
  candles: { time: number; open: number; high: number; low: number; close: number }[];
  swings: { time: number; price: number; kind: "high" | "low"; confirmed: number }[];
  breaks: { time: number; from: number; level: number; kind: "BOS" | "CHoCH"; dir: number; displacement: boolean }[];
  zones: Zone[];
  levels: { kind: string; side: string; price: number; from: number; to: number }[];
  sweeps: { time: number; kind: string; dir: number; level: number; extreme: number }[];
  sessions: { name: string; from: number; to: number }[];
  trend: number; htf: number; range_pos: number | null;
};

const SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD"];
const TFS = ["M5", "M15", "H1", "H4"];
const LAYERS = [
  { id: "swings", label: "Swings" }, { id: "breaks", label: "BOS / CHoCH" }, { id: "ob", label: "Order blocks" },
  { id: "breaker", label: "Breakers" }, { id: "fvg", label: "FVGs" }, { id: "liquidity", label: "Liquidity + sweeps" },
  { id: "sessions", label: "Sessions / kill zones" }, { id: "spent", label: "Show used-up zones" },
] as const;
type Layer = (typeof LAYERS)[number]["id"];
const SESSION_TINT: Record<string, string> = { "Asia": "#a855f7", "London KZ": "#3b82f6", "NY AM KZ": "#22c55e", "Silver Bullet": "#f59e0b" };
const alpha = (hex: string, a: number) => hex + Math.round(a * 255).toString(16).padStart(2, "0");
const dirWord = (d: number) => (d > 0 ? "Bullish" : d < 0 ? "Bearish" : "Unclear");

/** Chart Lab (Phase 2): see exactly what the structure library detects on real candles, to verify it by eye. */
export default function ChartLab() {
  const cc = useChartColors();
  const [q, setQ] = useState({ symbol: "EURUSD", timeframe: "M15", bars: 600, end: "", swing_n: 3, displacement_k: 1.5, fvg_min_atr: 0.3 });
  const [on, setOn] = useState<Record<Layer, boolean>>({ swings: true, breaks: true, ob: true, breaker: false, fvg: true, liquidity: true, sessions: true, spent: false });
  const [d, setD] = useState<Resp | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const overlay = useRef<StructureOverlay | null>(null);
  const markers = useRef<ReturnType<typeof createSeriesMarkers<Time>> | null>(null);

  useEffect(() => {
    let dead = false;
    setLoading(true);
    const p = new URLSearchParams({ symbol: q.symbol, timeframe: q.timeframe, bars: String(q.bars), swing_n: String(q.swing_n),
      displacement_k: String(q.displacement_k), fvg_min_atr: String(q.fvg_min_atr), ...(q.end ? { end: `${q.end}T23:59:00Z` } : {}) });
    fetch(`${API}/structure?${p}`)
      .then(async (r) => { if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? `Request failed (${r.status})`); return r.json(); })
      .then((x: Resp) => { if (!dead) { setD(x); setErr(""); } })
      .catch((e) => { if (!dead) setErr(e.message); })
      .finally(() => { if (!dead) setLoading(false); });
    return () => { dead = true; };
  }, [q]);

  // chart shell (recreated on theme / symbol change)
  useEffect(() => {
    if (!box.current) return;
    const c = createChart(box.current, {
      autoSize: true, height: 560,
      layout: { background: { type: ColorType.Solid, color: cc.bg }, textColor: cc.axis, fontFamily: "JetBrains Mono, monospace", attributionLogo: true },
      grid: { vertLines: { color: cc.grid }, horzLines: { color: cc.grid } },
      rightPriceScale: { borderColor: cc.border }, timeScale: { borderColor: cc.border, timeVisible: true, secondsVisible: false },
      crosshair: { mode: CrosshairMode.Normal },
    });
    const jpy = q.symbol.endsWith("JPY"), xau = q.symbol.startsWith("XAU");
    const s = c.addSeries(CandlestickSeries, {
      upColor: cc.candleUp, downColor: cc.candleDown, borderUpColor: cc.candleUp, borderDownColor: cc.candleDown,
      wickUpColor: cc.candleUp, wickDownColor: cc.candleDown,
      priceFormat: { type: "price", precision: jpy ? 3 : xau ? 2 : 5, minMove: jpy ? 0.001 : xau ? 0.01 : 0.00001 },
    });
    const o = new StructureOverlay(cc.axis);
    s.attachPrimitive(o);
    chart.current = c; series.current = s; overlay.current = o;
    markers.current = createSeriesMarkers(s, []);
    return () => { c.remove(); chart.current = series.current = overlay.current = markers.current = null; };
  }, [cc, q.symbol]);

  const layers: OverlayData & { marks: SeriesMarker<Time>[] } = useMemo(() => {
    const out = { boxes: [] as Box[], segs: [] as Seg[], bands: [] as OverlayData["bands"], marks: [] as SeriesMarker<Time>[] };
    if (!d) return out;
    const bull = cc.up, bear = cc.down;
    if (on.sessions) for (const s of d.sessions) out.bands.push({ from: s.from, to: s.to, color: alpha(SESSION_TINT[s.name] ?? "#888888", 0.07), label: s.name });
    for (const z of d.zones) {
      const k = z.kind === "OB" ? "ob" : z.kind === "BREAKER" ? "breaker" : "fvg";
      if (!on[k as Layer]) continue;
      const spent = z.state === "invalidated" || z.state === "filled";
      if (spent && !on.spent) continue;
      const base = z.kind === "BREAKER" ? "#a855f7" : z.kind === "FVG" ? (z.dir > 0 ? "#14b8a6" : "#f97316") : z.dir > 0 ? bull : bear;
      const a = spent ? 0.05 : z.state === "mitigated" ? 0.12 : 0.22;
      out.boxes.push({ from: z.from, to: z.to, top: z.top, bottom: z.bottom, fill: alpha(base, a), stroke: alpha(base, spent ? 0.35 : 0.85),
        dashed: z.kind === "FVG", label: `${z.kind === "BREAKER" ? "BRK" : z.kind}${z.dir > 0 ? "+" : "−"}` });
    }
    if (on.breaks) for (const b of d.breaks) out.segs.push({
      from: b.from, to: b.time, price: b.level, color: b.dir > 0 ? bull : bear, dashed: b.kind === "CHoCH",
      label: `${b.kind}${b.displacement ? " ⚡" : ""}`, width: 1.5,
    });
    if (on.liquidity) {
      for (const lv of d.levels) out.segs.push({ from: lv.from, to: lv.to, price: lv.price, color: alpha(cc.axis, 0.9), dashed: true, label: lv.kind });
      for (const s of d.sweeps) out.marks.push({
        time: s.time as UTCTimestamp, position: s.dir > 0 ? "belowBar" : "aboveBar", shape: s.dir > 0 ? "arrowUp" : "arrowDown",
        color: "#f59e0b", text: `sweep ${s.kind.replace("SWING_", "")}`, size: 1,
      });
    }
    if (on.swings) for (const s of d.swings) out.marks.push({
      time: s.time as UTCTimestamp, position: s.kind === "high" ? "aboveBar" : "belowBar", shape: "circle",
      color: alpha(cc.axis, 0.9), size: 0.5, text: s.kind === "high" ? "H" : "L",
    });
    out.marks.sort((a, b) => (a.time as number) - (b.time as number));
    return out;
  }, [d, on, cc]);

  useEffect(() => {
    const s = series.current, c = chart.current;
    if (!s || !c || !d) return;
    s.setData(d.candles.map((k) => ({ ...k, time: k.time as UTCTimestamp })));
    c.timeScale().fitContent();
  }, [d, cc, q.symbol]);

  useEffect(() => {
    overlay.current?.setData(layers);
    markers.current?.setMarkers(layers.marks);
  }, [layers, d, cc, q.symbol]);

  const set = <K extends keyof typeof q>(k: K, v: (typeof q)[K]) => setQ((x) => ({ ...x, [k]: v }));
  const counts = d && {
    BOS: d.breaks.filter((b) => b.kind === "BOS").length, CHoCH: d.breaks.filter((b) => b.kind === "CHoCH").length,
    OB: d.zones.filter((z) => z.kind === "OB").length, FVG: d.zones.filter((z) => z.kind === "FVG").length, sweeps: d.sweeps.length,
  };

  return (
    <>
      <section className="desk-head" style={{ ["--dc" as string]: "#f59e0b" }}>
        <div className="lbl" style={{ color: "#f59e0b" }}>STRUCTURE LIBRARY</div>
        <h2>Chart Lab</h2>
        <p className="muted">Everything the SMC/ICT strategies "see", drawn on real Deriv candles: swings, BOS/CHoCH (⚡ = with displacement), order blocks, breakers,
          fair value gaps, liquidity levels and sweeps, and New York sessions. Each item is placed where it was <b>known</b> at the time, so this is exactly what a strategy could have acted on.</p>
      </section>

      <div className="panel lab-controls">
        <label>Pair<select value={q.symbol} onChange={(e) => set("symbol", e.target.value)}>{SYMBOLS.map((s) => <option key={s}>{s}</option>)}</select></label>
        <label>Timeframe<select value={q.timeframe} onChange={(e) => set("timeframe", e.target.value)}>{TFS.map((s) => <option key={s}>{s}</option>)}</select></label>
        <label>Candles<select value={q.bars} onChange={(e) => set("bars", +e.target.value)}>{[300, 600, 1200, 2000].map((s) => <option key={s}>{s}</option>)}</select></label>
        <label>Up to date<input type="date" value={q.end} onChange={(e) => set("end", e.target.value)} /></label>
        <label title="Bars each side that make a swing">Swing size<input type="number" min={1} max={10} value={q.swing_n} onChange={(e) => set("swing_n", +e.target.value)} /></label>
        <label title="Body must be at least this many ATRs">Displacement ×ATR<input type="number" step={0.1} min={0.5} max={5} value={q.displacement_k} onChange={(e) => set("displacement_k", +e.target.value)} /></label>
        <label title="Ignore gaps smaller than this many ATRs">Min FVG ×ATR<input type="number" step={0.1} min={0} max={3} value={q.fvg_min_atr} onChange={(e) => set("fvg_min_atr", +e.target.value)} /></label>
        {loading && <RefreshCw size={16} className="spin muted" aria-label="Loading" />}
      </div>

      <div className="lab-toggles" role="group" aria-label="Layers">
        {LAYERS.map((l) => (
          <button key={l.id} className={`chip x ${on[l.id] ? "on" : ""}`} aria-pressed={on[l.id]} onClick={() => setOn((o) => ({ ...o, [l.id]: !o[l.id] }))}>{l.label}</button>
        ))}
      </div>

      {err && <div className="banner">{err}</div>}
      {d && counts && (
        <div className="lab-summary">
          <span>Structure: <b className={d.trend > 0 ? "up" : d.trend < 0 ? "down" : ""}>{dirWord(d.trend)}</b></span>
          <span>H4 bias: <b className={d.htf > 0 ? "up" : d.htf < 0 ? "down" : ""}>{dirWord(d.htf)}</b></span>
          {d.range_pos != null && <span>Price is in <b>{d.range_pos > 0.5 ? "premium" : "discount"}</b> ({Math.round(d.range_pos * 100)}% of range)</span>}
          <span className="muted">{counts.BOS} BOS · {counts.CHoCH} CHoCH · {counts.OB} OB · {counts.FVG} FVG · {counts.sweeps} sweeps</span>
        </div>
      )}
      <div className="panel"><div ref={box} className="lab-chart" role="img" aria-label={`${q.symbol} ${q.timeframe} chart with market structure overlays`} /></div>
      <p className="muted small" style={{ lineHeight: 1.6 }}>
        Green/red boxes = bullish/bearish order blocks · dashed teal/orange = bullish/bearish FVGs · purple = breakers (failed order blocks) ·
        dotted grey lines = liquidity (PDH/PDL previous day, PWH/PWL previous week, ASIA_H/L, EQH/EQL equal highs/lows), ending where swept ·
        orange arrows = sweeps · lines from a swing to the breaking candle = BOS (solid) / CHoCH (dashed). Faded boxes were already touched.
      </p>
    </>
  );
}
