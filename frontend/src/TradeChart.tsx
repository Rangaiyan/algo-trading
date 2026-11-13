import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries, ColorType, CrosshairMode, LineStyle, createChart, createSeriesMarkers,
  type IChartApi, type ISeriesApi, type SeriesMarker, type Time, type UTCTimestamp,
} from "lightweight-charts";
import { ChevronLeft, ChevronRight, SkipForward } from "lucide-react";
import { type Candle, type Trade, getCandles } from "./api";
import { useChartColors } from "./theme";

const BAR_MIN: Record<string, number> = { M1: 1, M5: 5, M15: 15, M30: 30, H1: 60, H4: 240, D1: 1440 };
const sec = (iso: string) => Math.floor(new Date(iso).getTime() / 1000);
const money = (n: number) => `${n < 0 ? "-" : "+"}$${Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;

/**
 * Price chart for a backtest: real candles with every trade's entry (arrow) and exit (dot) marked.
 * With a trade selected, the chart centres on it and draws its entry, stop-loss and take-profit levels.
 */
export default function TradeChart({ symbol, timeframe, end, trades, selected, onSelect }: {
  symbol: string; timeframe: string; end: string; trades: Trade[];
  selected: number | null; onSelect: (i: number | null) => void;
}) {
  const cc = useChartColors();
  const box = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [err, setErr] = useState("");
  const onSelectRef = useRef(onSelect);
  useEffect(() => { onSelectRef.current = onSelect; }, [onSelect]);

  // 1) fetch the window: around the selected trade, or the last 1,500 bars of the run
  const t = selected != null ? trades[selected] : null;
  useEffect(() => {
    let dead = false;
    const pad = (BAR_MIN[timeframe] ?? 15) * 60 * 1000 * 120; // ~120 bars of context each side
    const opts = t
      ? { start: new Date(new Date(t.entry_ts).getTime() - pad).toISOString(), end: new Date(new Date(t.exit_ts).getTime() + pad).toISOString(), limit: 5000 }
      : { end, limit: 1500 };
    getCandles(symbol, timeframe, opts).then((c) => { if (!dead) { setCandles(c); setErr(""); } }).catch((e) => !dead && setErr(e.message));
    return () => { dead = true; };
  }, [symbol, timeframe, end, t]);

  // 2) create the chart once per theme
  useEffect(() => {
    if (!box.current) return;
    const c = createChart(box.current, {
      autoSize: true, height: 420,
      layout: { background: { type: ColorType.Solid, color: cc.bg }, textColor: cc.axis, fontFamily: "JetBrains Mono, monospace", attributionLogo: true },
      grid: { vertLines: { color: cc.grid }, horzLines: { color: cc.grid } },
      rightPriceScale: { borderColor: cc.border }, timeScale: { borderColor: cc.border, timeVisible: true, secondsVisible: false },
      crosshair: { mode: CrosshairMode.Normal },
    });
    series.current = c.addSeries(CandlestickSeries, {
      upColor: cc.candleUp, downColor: cc.candleDown, borderUpColor: cc.candleUp, borderDownColor: cc.candleDown,
      wickUpColor: cc.candleUp, wickDownColor: cc.candleDown,
      priceFormat: { type: "price", precision: symbol.endsWith("JPY") ? 3 : symbol.startsWith("XAU") ? 2 : 5, minMove: symbol.endsWith("JPY") ? 0.001 : symbol.startsWith("XAU") ? 0.01 : 0.00001 },
    });
    chart.current = c;
    return () => { c.remove(); chart.current = null; series.current = null; };
  }, [cc, symbol]);

  // 3) draw candles, markers and the selected trade's levels
  useEffect(() => {
    const c = chart.current, s = series.current;
    if (!c || !s || candles.length === 0) return;
    s.setData(candles.map((k) => ({ ...k, time: k.time as UTCTimestamp })));
    const lo = candles[0].time, hi = candles[candles.length - 1].time;
    const markers: SeriesMarker<Time>[] = [];
    trades.forEach((tr, i) => {
      const en = sec(tr.entry_ts), ex = sec(tr.exit_ts), buy = tr.side === "buy", sel = i === selected;
      if (en >= lo && en <= hi) markers.push({
        time: en as UTCTimestamp, position: buy ? "belowBar" : "aboveBar", shape: buy ? "arrowUp" : "arrowDown",
        color: buy ? "#3b82f6" : "#f59e0b", size: sel ? 2 : 1, text: sel || trades.length < 60 ? (buy ? "BUY" : "SELL") : "",
      });
      if (ex >= lo && ex <= hi) markers.push({
        time: ex as UTCTimestamp, position: buy ? "aboveBar" : "belowBar", shape: "circle",
        color: tr.pnl >= 0 ? cc.up : cc.down, size: sel ? 2 : 1, text: sel ? money(tr.pnl) : "",
      });
    });
    markers.sort((a, b) => (a.time as number) - (b.time as number));
    const m = createSeriesMarkers(s, markers);
    const lines = t ? [
      s.createPriceLine({ price: t.entry_px, color: "#3b82f6", lineWidth: 1, lineStyle: LineStyle.Solid, axisLabelVisible: true, title: "ENTRY" }),
      ...(t.stop_loss ? [s.createPriceLine({ price: t.stop_loss, color: cc.down, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "SL" })] : []),
      ...(t.take_profit ? [s.createPriceLine({ price: t.take_profit, color: cc.up, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "TP" })] : []),
      s.createPriceLine({ price: t.exit_px, color: t.pnl >= 0 ? cc.up : cc.down, lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: true, title: "EXIT" }),
    ] : [];
    if (t) {
      const span = Math.max(sec(t.exit_ts) - sec(t.entry_ts), 1);
      c.timeScale().setVisibleRange({ from: (sec(t.entry_ts) - span * 1.5 - 3600) as UTCTimestamp, to: (sec(t.exit_ts) + span * 1.5 + 3600) as UTCTimestamp });
    } else {
      c.timeScale().setVisibleLogicalRange({ from: candles.length - 300, to: candles.length + 5 });
    }
    // click a marker's bar -> select that trade
    const click = (p: { time?: Time }) => {
      if (p.time === undefined) return;
      const at = p.time as number;
      const hit = trades.findIndex((tr) => sec(tr.entry_ts) === at || sec(tr.exit_ts) === at);
      if (hit >= 0) onSelectRef.current(hit);
    };
    c.subscribeClick(click);
    return () => { m.detach(); lines.forEach((l) => s.removePriceLine(l)); c.unsubscribeClick(click); };
  }, [candles, trades, selected, t, cc]);

  const go = (d: number) => {
    if (!trades.length) return;
    onSelect(selected == null ? (d > 0 ? 0 : trades.length - 1) : Math.min(trades.length - 1, Math.max(0, selected + d)));
  };

  return (
    <div className="panel tchart">
      <div className="tchart-head">
        <h3>Price chart <small className="muted">{symbol} {timeframe} · ▲▼ entry · ● exit (green win / red loss)</small></h3>
        <span className="sh-spacer" />
        <button className="pill" onClick={() => go(-1)} disabled={!trades.length} aria-label="Previous trade"><ChevronLeft size={14} /> Prev</button>
        <span className="muted tchart-pos">{selected != null ? `Trade ${selected + 1} / ${trades.length}` : `${trades.length} trades`}</span>
        <button className="pill" onClick={() => go(1)} disabled={!trades.length} aria-label="Next trade">Next <ChevronRight size={14} /></button>
        <button className="pill" onClick={() => onSelect(null)} disabled={selected == null} title="Back to the end of the run"><SkipForward size={14} /> Latest</button>
      </div>
      {t && (
        <div className="tchart-info">
          <span className={`side-badge ${t.side}`}>{t.side === "buy" ? "LONG" : "SHORT"}</span>
          <span>{t.entry_ts.slice(0, 16).replace("T", " ")} → {t.exit_ts.slice(0, 16).replace("T", " ")} UTC</span>
          <span>in <b>{t.entry_px}</b> · out <b>{t.exit_px}</b></span>
          {t.stop_loss && <span>SL <b>{t.stop_loss}</b></span>}
          {t.take_profit && <span>TP <b>{t.take_profit}</b></span>}
          <span>{t.qty} lots · {t.bars_held} bars · {t.exit_reason}</span>
          <span>{t.pips} pips · {t.r_multiple}R</span>
          <b className={t.pnl >= 0 ? "pos" : "neg"}>{money(t.pnl)}</b>
        </div>
      )}
      {err ? <p className="err">{err}</p> : <div ref={box} className="tchart-box" role="img" aria-label={`${symbol} ${timeframe} candlestick chart with backtest trades`} />}
    </div>
  );
}
