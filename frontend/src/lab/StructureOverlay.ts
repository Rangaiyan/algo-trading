import type {
  IChartApi, IPrimitivePaneRenderer, IPrimitivePaneView, ISeriesApi, ISeriesPrimitive, PrimitivePaneViewZOrder,
  SeriesAttachedParameter, SeriesType, Time, UTCTimestamp,
} from "lightweight-charts";

type DrawTarget = Parameters<IPrimitivePaneRenderer["draw"]>[0];

export type Box = { from: number; to: number; top: number; bottom: number; fill: string; stroke: string; dashed?: boolean; label?: string };
export type Seg = { from: number; to: number; price: number; color: string; dashed?: boolean; label?: string; width?: number };
export type Band = { from: number; to: number; color: string; label?: string };
export type OverlayData = { boxes: Box[]; segs: Seg[]; bands: Band[] };

/** Draws session bands (background), zones (boxes) and levels / structure breaks (segments) on a candle series. */
export class StructureOverlay implements ISeriesPrimitive<Time> {
  private chart: IChartApi | null = null;
  private series: ISeriesApi<SeriesType> | null = null;
  private requestUpdate: (() => void) | null = null;
  private data: OverlayData = { boxes: [], segs: [], bands: [] };
  private readonly views: readonly IPrimitivePaneView[];

  private readonly text: string;

  constructor(text: string) {
    this.text = text;
    const bg: IPrimitivePaneView = { zOrder: (): PrimitivePaneViewZOrder => "bottom", renderer: () => this.renderer(true) };
    const fg: IPrimitivePaneView = { zOrder: (): PrimitivePaneViewZOrder => "normal", renderer: () => this.renderer(false) };
    this.views = [bg, fg];
  }

  attached(p: SeriesAttachedParameter<Time>) {
    this.chart = p.chart as IChartApi;
    this.series = p.series;
    this.requestUpdate = p.requestUpdate;
  }

  detached() { this.chart = this.series = this.requestUpdate = null; }

  setData(d: OverlayData) { this.data = d; this.requestUpdate?.(); }

  paneViews() { return this.views; }

  private x(t: number): number | null {
    return this.chart?.timeScale().timeToCoordinate(t as UTCTimestamp) ?? null;
  }

  private y(p: number): number | null {
    return this.series?.priceToCoordinate(p) ?? null;
  }

  private renderer(background: boolean): IPrimitivePaneRenderer {
    return {
      draw: (target: DrawTarget) => {
        target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
          ctx.font = "10px JetBrains Mono, monospace";
          if (background) {
            for (const b of this.data.bands) {
              const x1 = this.x(b.from), x2 = this.x(b.to);
              if (x1 === null || x2 === null) continue;
              ctx.fillStyle = b.color;
              ctx.fillRect(x1, 0, Math.max(2, x2 - x1), mediaSize.height);
              if (b.label && x2 - x1 > 40) { ctx.fillStyle = this.text; ctx.globalAlpha = 0.55; ctx.fillText(b.label, x1 + 3, 12); ctx.globalAlpha = 1; }
            }
            return;
          }
          for (const b of this.data.boxes) {
            const x1 = this.x(b.from), x2 = this.x(b.to), y1 = this.y(b.top), y2 = this.y(b.bottom);
            if (x1 === null || x2 === null || y1 === null || y2 === null) continue;
            const w = Math.max(3, x2 - x1), h = Math.max(1, y2 - y1);
            ctx.fillStyle = b.fill;
            ctx.fillRect(x1, y1, w, h);
            ctx.strokeStyle = b.stroke;
            ctx.lineWidth = 1;
            ctx.setLineDash(b.dashed ? [4, 3] : []);
            ctx.strokeRect(x1 + 0.5, y1 + 0.5, w - 1, h - 1);
            if (b.label && w > 24 && h > 9) { ctx.fillStyle = b.stroke; ctx.fillText(b.label, x1 + 3, y1 + 10); }
          }
          for (const s of this.data.segs) {
            const x1 = this.x(s.from), x2 = this.x(s.to), y = this.y(s.price);
            if (x1 === null || x2 === null || y === null) continue;
            ctx.strokeStyle = s.color;
            ctx.lineWidth = s.width ?? 1;
            ctx.setLineDash(s.dashed ? [5, 4] : []);
            ctx.beginPath(); ctx.moveTo(x1, y + 0.5); ctx.lineTo(Math.max(x2, x1 + 4), y + 0.5); ctx.stroke();
            if (s.label) { ctx.fillStyle = s.color; ctx.fillText(s.label, (x1 + Math.max(x2, x1 + 4)) / 2 - s.label.length * 3, y - 3); }
          }
          ctx.setLineDash([]);
        });
      },
    };
  }
}
