"""SMC strategies (doc 8.2) on the structure library. All entries are limit orders at a zone unless stated."""
from __future__ import annotations

import numpy as np

from app.domain import Bar, Signal
from app.patterns.candles import bearish_engulfing, bearish_pin_bar, bullish_engulfing, bullish_pin_bar
from app.strategies.structure_base import StructureStrategy


class SMCSweepChoch(StructureStrategy):
    """SMC-1 (doc 8.2): liquidity sweep, then CHoCH with displacement, enter on the retrace into the OB/FVG."""

    name = "SMC-1"
    defaults = {"window": 30, "need_displacement": True, "use_htf": False, "pd_filter": True, "zone": "ob", "entry": "edge"}

    def on_bar(self, ctx, bar: Bar) -> list[Signal]:
        i = self.bind(ctx)
        self.observe(i)
        for bi, b in self.breaks_now(i):
            d = b.direction
            if b.kind != "CHoCH" or (self.p("need_displacement") and not b.displacement):
                continue
            s = self.last_sweep.get(d)
            if s is None or i - s.i > self.p("window") or s.i > i:
                continue
            if self.p("use_htf") and self.a.htf[i] != d:
                continue
            z = self.entry_zone(bi, b, i, self.p("zone"))
            if z is None or np.isnan(self.atr[i]):
                continue
            entry = (z.top if d > 0 else z.bottom) if self.p("entry") == "edge" else z.mid
            if self.p("pd_filter"):
                # dealing range of the reversal leg: sweep-side extreme -> furthest price since
                if d > 0:
                    lo, hi = b.leg_price, max(self.h[b.leg_i:i + 1])
                else:
                    lo, hi = min(self.l[b.leg_i:i + 1]), b.leg_price
                if hi > lo and ((entry - lo) / (hi - lo) - 0.5) * d > 0:
                    continue  # longs only in discount, shorts only in premium
            sl = s.extreme - d * self.p("sl_buffer_atr") * self.atr[i]
            risk = abs(entry - sl)
            return self.order(d, entry, sl, self.target(d, entry, risk, i), f"sweep {s.level.kind} + CHoCH")
        return []


class SMCBosRetest(StructureStrategy):
    """SMC-2 (doc 8.2): trend continuation; BOS with displacement, enter on the first retest of its order block."""

    name = "SMC-2"
    defaults = {"use_htf": True, "need_displacement": True, "pd_filter": True}

    def on_bar(self, ctx, bar: Bar) -> list[Signal]:
        i = self.bind(ctx)
        self.observe(i)
        for bi, b in self.breaks_now(i):
            d = b.direction
            if b.kind != "BOS" or (self.p("need_displacement") and not b.displacement):
                continue
            if self.p("use_htf") and self.a.htf[i] != d:
                continue
            z = self.zones_by_break.get(bi)
            if z is None or np.isnan(self.atr[i]):
                continue
            entry = z.top if d > 0 else z.bottom
            if self.p("pd_filter"):
                ext = max(self.h[b.leg_i:i + 1]) if d > 0 else min(self.l[b.leg_i:i + 1])
                if ext != b.leg_price and ((entry - b.leg_price) / (ext - b.leg_price)) > 0.5:
                    continue  # OB must sit in the discount (long) / premium (short) half of the leg
            sl = (z.bottom if d > 0 else z.top) - d * self.p("sl_buffer_atr") * self.atr[i]
            risk = abs(entry - sl)
            return self.order(d, entry, sl, entry + d * self.p("rr") * risk, "BOS + OB retest")
        return []


class SMCFvgMitigation(StructureStrategy):
    """SMC-3 (doc 8.2): price returns into an unmitigated FVG aligned with bias and prints a reaction candle."""

    name = "SMC-3"
    defaults = {"use_htf": True, "max_wait": 200}

    def on_start(self, ctx):
        super().on_start(ctx)
        df = ctx.df
        self.bull_rx = (bullish_engulfing(df) | bullish_pin_bar(df)).to_numpy()
        self.bear_rx = (bearish_engulfing(df) | bearish_pin_bar(df)).to_numpy()
        self.watch = []

    def on_bar(self, ctx, bar: Bar) -> list[Signal]:
        i = self.bind(ctx)
        self.observe(i)
        bias = self.a.htf[i] if self.p("use_htf") else self.a.ms.trend[i]
        self.watch = [z for z in self.watch if z.active(i) and i - z.created_i <= self.p("max_wait")
                      and (z.mitigated_i is None or z.mitigated_i >= i)]
        out: list[Signal] = []
        for z in self.watch:
            if z.mitigated_i != i or z.direction != bias or np.isnan(self.atr[i]):
                continue
            rx = self.bull_rx[i] and self.c[i] > z.mid if z.direction > 0 else self.bear_rx[i] and self.c[i] < z.mid
            if not rx:
                continue
            d = z.direction
            sl = (z.bottom if d > 0 else z.top) - d * self.p("sl_buffer_atr") * self.atr[i]
            sl = min(sl, self.l[i] - self.p("sl_buffer_atr") * self.atr[i]) if d > 0 else max(sl, self.h[i] + self.p("sl_buffer_atr") * self.atr[i])
            risk = abs(self.c[i] - sl)
            out = self.order(d, None, sl, self.c[i] + d * self.p("rr") * risk, "FVG mitigation + reaction")
            break
        self.watch.extend(self.a.fvgs_at[i])  # gaps formed this bar can be traded from the next bar
        return out
