"""ICT strategies (doc 8.3). Time windows are New York local time with DST."""
from __future__ import annotations

from datetime import time

import numpy as np

from app.domain import Bar, Signal
from app.strategies.structure_base import StructureStrategy
from app.structure import in_ny_window, trading_day


def _t(s: str) -> time:
    hh, mm = s.split(":")
    return time(int(hh), int(mm))


class ICTAsiaRaid(StructureStrategy):
    """ICT-1 (doc 8.3): Asia range, London kill-zone sweep of one side (Judas), CHoCH back, target the other side."""

    name = "ICT-1"
    defaults = {"kill_zone": ("02:00", "05:00"), "setup_until": "08:00", "window": 24, "need_displacement": True}

    def on_start(self, ctx):
        super().on_start(ctx)
        idx = ctx.df.index
        self.in_kz = in_ny_window(idx, *map(_t, self.p("kill_zone")))
        self.in_setup = in_ny_window(idx, _t(self.p("kill_zone")[0]), _t(self.p("setup_until")))
        self.day = trading_day(idx)
        self.raid: dict = {}        # trading day -> latest Asia sweep
        self.traded: set = set()

    def on_bar(self, ctx, bar: Bar) -> list[Signal]:
        i = self.bind(ctx)
        self.observe(i)
        day = self.day[i]
        for s in self.a.sweeps_at[i]:
            if s.level.kind in ("ASIA_H", "ASIA_L") and self.in_kz[i]:
                self.raid[day] = s
        s = self.raid.get(day)
        if s is None or day in self.traded or not self.in_setup[i] or i - s.i > self.p("window"):
            return []
        for bi, b in self.breaks_now(i):
            d = b.direction
            if d != s.direction or b.kind != "CHoCH" or (self.p("need_displacement") and not b.displacement):
                continue
            z = self.entry_zone(bi, b, i, "fvg")
            if z is None or np.isnan(self.atr[i]):
                continue
            entry = z.top if d > 0 else z.bottom
            sl = s.extreme - d * self.p("sl_buffer_atr") * self.atr[i]
            risk = abs(entry - sl)
            tp = self.a.asia_high[i] if d > 0 else self.a.asia_low[i]   # the opposite side of the Asia range ...
            if np.isnan(tp) or (tp - entry) * d < self.p("min_rr") * risk:
                tp = self.target(d, entry, risk, i)                     # ... or the next liquidity pool (doc 8.3)
            self.traded.add(day)
            return self.order(d, entry, sl, tp, f"Asia {'low' if d > 0 else 'high'} raid + CHoCH")
        return []


class ICTOte(StructureStrategy):
    """ICT-2 (doc 8.3): after displacement + structure shift, buy/sell the 62-79% retracement (70.5% default)."""

    name = "ICT-2"
    defaults = {"ote": 0.705, "ote_band": (0.62, 0.79), "target_ext": 0.27, "kinds": ("CHoCH",),
                "require_fvg": False, "need_displacement": True, "use_htf": False}

    def on_bar(self, ctx, bar: Bar) -> list[Signal]:
        i = self.bind(ctx)
        self.observe(i)
        for _, b in self.breaks_now(i):
            d = b.direction
            if b.kind not in self.p("kinds") or (self.p("need_displacement") and not b.displacement):
                continue
            if self.p("use_htf") and self.a.htf[i] != d:
                continue
            start = b.leg_price
            end = max(self.h[b.leg_i:i + 1]) if d > 0 else min(self.l[b.leg_i:i + 1])
            rng = abs(end - start)
            if rng <= 0 or np.isnan(self.atr[i]):
                continue
            entry = end - d * self.p("ote") * rng
            if self.p("require_fvg"):
                lo_b, hi_b = self.p("ote_band")
                band = sorted((end - d * lo_b * rng, end - d * hi_b * rng))
                if not any(z.direction == d and z.active(i) and z.bottom <= band[1] and z.top >= band[0]
                           for j in range(b.leg_i, i + 1) for z in self.a.fvgs_at[j]):
                    continue
            sl = start - d * self.p("sl_buffer_atr") * self.atr[i]
            tp = end + d * self.p("target_ext") * rng
            return self.order(d, entry, sl, tp, f"OTE {self.p('ote'):.3f} of the impulse")
        return []


class ICTSilverBullet(StructureStrategy):
    """ICT-3 (doc 8.3): inside the Silver Bullet hours, take the first FVG toward the draw on liquidity."""

    name = "ICT-3"
    defaults = {"windows": (("03:00", "04:00"), ("10:00", "11:00"), ("14:00", "15:00")), "require_sweep": True,
                "sweep_lookback": 40, "expires_bars": 6}

    def on_start(self, ctx):
        super().on_start(ctx)
        idx = ctx.df.index
        self.win = np.full(len(idx), -1)
        for k, (s, e) in enumerate(self.p("windows")):
            self.win[in_ny_window(idx, _t(s), _t(e))] = k
        self.day = trading_day(idx)
        self.used: set = set()

    def on_bar(self, ctx, bar: Bar) -> list[Signal]:
        i = self.bind(ctx)
        self.observe(i)
        w = self.win[i]
        if w < 0 or (self.day[i], w) in self.used or np.isnan(self.atr[i]):
            return []
        for z in self.a.fvgs_at[i]:
            d = z.direction
            if self.p("require_sweep"):
                s = self.last_sweep.get(d)
                if s is None or i - s.i > self.p("sweep_lookback"):
                    continue  # draw on liquidity: a sell-side sweep points up, a buy-side sweep points down
            first_low, first_high = self.l[z.origin_i - 1], self.h[z.origin_i - 1]   # candle 1 of the gap
            entry = z.top if d > 0 else z.bottom
            sl = (first_low if d > 0 else first_high) - d * self.p("sl_buffer_atr") * self.atr[i]
            self.used.add((self.day[i], w))
            return self.order(d, entry, sl, entry + d * self.p("rr") * abs(entry - sl), f"Silver Bullet window {w + 1}")
        return []
