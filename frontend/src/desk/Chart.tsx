import { useEffect, useRef } from "react";
import { CandlestickSeries, ColorType, CrosshairMode, createChart, createSeriesMarkers, type IChartApi, type UTCTimestamp } from "lightweight-charts";
import type { ChartData } from "../api";

export type Line = { price: number; color: string; title: string };

export default function Chart({ data, labels, lines, selectedTrade, onTradeClick }: {
  data: ChartData; labels: boolean; lines: Line[]; selectedTrade?: number | null; onTradeClick: (tradeId: number) => void;
}) {
  const el = useRef<HTMLDivElement>(null);
  const cb = useRef(onTradeClick);
  cb.current = onTradeClick;

  useEffect(() => {
    if (!el.current) return;
    const chart: IChartApi = createChart(el.current, {
      autoSize: true, height: 380,
      layout: { background: { type: ColorType.Solid, color: "#0e1015" }, textColor: "#7a8196", fontFamily: "JetBrains Mono, monospace", attributionLogo: true },
      grid: { vertLines: { color: "#1a1d26" }, horzLines: { color: "#1a1d26" } },
      rightPriceScale: { borderColor: "#23232f" }, timeScale: { borderColor: "#23232f", timeVisible: true, secondsVisible: false },
      crosshair: { mode: CrosshairMode.Normal },
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#26a65b", downColor: "#e0443f", borderUpColor: "#26a65b", borderDownColor: "#e0443f", wickUpColor: "#26a65b", wickDownColor: "#e0443f",
      priceFormat: { type: "price", precision: data.symbol.endsWith("JPY") ? 3 : 5, minMove: data.symbol.endsWith("JPY") ? 0.001 : 0.00001 },
    });
    series.setData(data.candles.map((c) => ({ ...c, time: c.time as UTCTimestamp })));
    createSeriesMarkers(series, data.markers.map((m) => {
      const entry = m.kind === "entry", buy = m.side === "buy";
      const sel = selectedTrade === m.trade_id;
      return {
        time: m.time as UTCTimestamp,
        position: (entry ? buy : !buy) ? ("belowBar" as const) : ("aboveBar" as const),
        shape: entry ? (buy ? ("arrowUp" as const) : ("arrowDown" as const)) : ("circle" as const),
        color: entry ? (buy ? "#4f8cff" : "#f59e0b") : m.pnl >= 0 ? "#22c55e" : "#ef4444",
        size: sel ? 2 : 1,
        text: labels ? (entry ? (buy ? "BUY" : "SELL") : `${m.pnl >= 0 ? "+" : ""}${m.pnl.toFixed(0)}`) : "",
      };
    }));
    lines.forEach((l) => series.createPriceLine({ price: l.price, color: l.color, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: l.title }));
    chart.timeScale().fitContent();
    chart.subscribeClick((p) => {
      if (p.time === undefined) return;
      const hit = data.markers.find((m) => m.time === (p.time as number));
      if (hit) cb.current(hit.trade_id);
    });
    return () => chart.remove();
  }, [data, labels, lines, selectedTrade]);

  return <div ref={el} style={{ width: "100%", height: 380 }} role="img" aria-label={`${data.symbol} ${data.timeframe} candlestick chart with trade markers`} />;
}
