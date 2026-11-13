"""Market structure (doc 8.1): trend, BOS / CHoCH on candle CLOSE, displacement, order blocks, breakers.

One forward pass over closed bars; every object records the bar index at which it became known,
and later facts about it (mitigated_i, invalidated_i) are only ever set at the bar they happen.
Strategies must compare those indices with the current bar (`<= i`) and never peek further.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.indicators.core import atr
from app.structure.swings import Swing, by_confirmation, swings


@dataclass
class Break:
    i: int                 # bar whose CLOSE broke the swing
    kind: str              # "BOS" (with the trend) | "CHoCH" (against it)
    direction: int         # +1 bullish break (close above a swing high), -1 bearish
    level: float           # the swing price that was broken
    swing_i: int           # pivot bar of the broken swing
    leg_i: int             # bar of the leg extreme the move started from (lowest low before a bullish break)
    leg_price: float
    displacement: bool     # a big-bodied candle (>= k x ATR) in the break direction within the leg


@dataclass
class Zone:
    """An order block / breaker / FVG price zone. top > bottom."""
    kind: str              # "OB" | "BREAKER" | "FVG"
    direction: int         # +1 bullish (demand: buy on retest), -1 bearish (supply)
    top: float
    bottom: float
    created_i: int         # usable from this bar on
    origin_i: int          # candle the zone was taken from
    mitigated_i: int | None = None     # first bar after creation that traded into the zone
    filled_i: int | None = None        # FVG: price traded all the way through
    invalidated_i: int | None = None   # bar that CLOSED through the far side
    source_break: int | None = None    # index into Structure.breaks
    expires_i: int | None = None       # zones stop being tracked (and are inactive) from this bar
    meta: dict = field(default_factory=dict)

    @property
    def mid(self) -> float:
        return (self.top + self.bottom) / 2

    def active(self, i: int) -> bool:
        """Created and not yet invalidated as of bar i (mitigation alone does not end a zone)."""
        return (self.created_i <= i and (self.invalidated_i is None or self.invalidated_i > i)
                and (self.expires_i is None or i < self.expires_i))

    def fresh(self, i: int) -> bool:
        """Active and never touched before bar i (first retest still possible)."""
        return self.active(i) and (self.mitigated_i is None or self.mitigated_i >= i)


@dataclass
class Structure:
    swings: list[Swing]
    breaks: list[Break]
    trend: np.ndarray            # per bar after its close: +1 / -1 / 0
    last_high: np.ndarray        # most recent confirmed swing high price known at bar i
    last_low: np.ndarray
    zones: list[Zone]            # order blocks and breakers
    atr: np.ndarray
    breaks_at: list[list[int]]   # per bar: indices into `breaks` that happened on that bar


def track_zone(z: Zone, i: int, high: float, low: float, close: float, max_age: int) -> list[Zone]:
    """Update a zone with bar i. Returns a new breaker zone if an order block just failed."""
    born: list[Zone] = []
    if z.invalidated_i is not None or i <= z.created_i:
        return born
    if z.mitigated_i is None and low <= z.top and high >= z.bottom:
        z.mitigated_i = i
    if z.kind == "FVG" and z.filled_i is None and (low <= z.bottom if z.direction > 0 else high >= z.top):
        z.filled_i = i
    if z.direction > 0 and close < z.bottom or z.direction < 0 and close > z.top:
        z.invalidated_i = i
        if z.kind == "OB":  # failed order block -> breaker of the opposite direction (doc 8.1)
            born.append(Zone("BREAKER", -z.direction, z.top, z.bottom, i, z.origin_i, expires_i=i + max_age,
                             meta={"from_ob": z.origin_i}))
    return born


def track_all(live: list[Zone], i: int, high: float, low: float, close: float, max_age: int) -> list[Zone]:
    """Advance live zones by one bar; drop dead/expired ones from `live`. Returns zones born this bar."""
    born: list[Zone] = []
    for z in live:
        born.extend(track_zone(z, i, high, low, close, max_age))
    live[:] = [z for z in live if z.invalidated_i is None and (z.expires_i is None or i + 1 < z.expires_i)]
    return born


def analyze(df: pd.DataFrame, n: int = 3, displacement_k: float = 1.5, ob_zone: str = "body",
            ob_lookback: int = 10, zone_max_age: int = 500) -> Structure:
    o, h, lo, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    a = atr(df).to_numpy()
    length = len(df)
    sw = swings(df, n)
    known = by_confirmation(sw, length)
    trend = np.zeros(length, dtype=int)
    last_hi, last_lo = np.full(length, np.nan), np.full(length, np.nan)
    breaks: list[Break] = []
    breaks_at: list[list[int]] = [[] for _ in range(length)]
    zones: list[Zone] = []
    live: list[Zone] = []

    cur_trend = 0
    sh: Swing | None = None   # last confirmed, not yet broken swing high
    sl: Swing | None = None
    lh = ll = np.nan
    for i in range(length):
        for s in known[i]:
            if s.kind == "high":
                sh, lh = s, s.price
            else:
                sl, ll = s, s.price
        born = track_all(live, i, h[i], lo[i], c[i], zone_max_age)
        zones.extend(born)
        live.extend(born)

        for broken, direction in ((sh, 1), (sl, -1)):
            if broken is None:
                continue
            if (direction > 0 and c[i] > broken.price) or (direction < 0 and c[i] < broken.price):
                kind = "CHoCH" if cur_trend == -direction else "BOS"
                # leg extreme: the lowest low (bullish) / highest high (bearish) between the swing and this bar
                seg = slice(broken.i, i + 1)
                leg_i = broken.i + int(np.argmin(lo[seg]) if direction > 0 else np.argmax(h[seg]))
                leg_price = float(lo[leg_i] if direction > 0 else h[leg_i])
                body = (c[leg_i:i + 1] - o[leg_i:i + 1]) * direction
                disp = bool(np.nanmax(body - displacement_k * a[leg_i:i + 1], initial=-np.inf) >= 0) \
                    if not np.all(np.isnan(a[leg_i:i + 1])) else False
                b = Break(i, kind, direction, broken.price, broken.i, leg_i, leg_price, disp)
                breaks.append(b)
                breaks_at[i].append(len(breaks) - 1)
                cur_trend = direction
                # order block: last opposite-coloured candle at/before the leg extreme
                for j in range(leg_i, max(leg_i - ob_lookback, -1), -1):
                    if (c[j] - o[j]) * direction < 0:
                        top, bot = (max(o[j], c[j]), min(o[j], c[j])) if ob_zone == "body" else (h[j], lo[j])
                        if top > bot:
                            z = Zone("OB", direction, float(top), float(bot), i, j, source_break=len(breaks) - 1,
                                     expires_i=i + zone_max_age, meta={"displacement": disp})
                            zones.append(z)
                            live.append(z)
                        break
                if direction > 0:
                    sh = None
                else:
                    sl = None
        trend[i], last_hi[i], last_lo[i] = cur_trend, lh, ll
    return Structure(sw, breaks, trend, last_hi, last_lo, zones, a, breaks_at)
