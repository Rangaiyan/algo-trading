"""Shared plumbing for SMC / ICT strategies: build the structure analysis once, then expose causal helpers.

Rule for subclasses: at bar i only use objects whose known-at index (created_i / i / conf_i) is <= i, and
compare mitigation/invalidation indices against i. The non-repainting signal test enforces this.
"""
from __future__ import annotations

import numpy as np

from app.domain import Side, Signal
from app.strategies.base import Strategy
from app.structure import Analysis, Break, Zone, analyze_all

_CACHE: dict[tuple, Analysis] = {}
_CACHE_MAX = 10


def cached_analysis(df, **kw) -> Analysis:
    """The structure analysis depends only on the candles and the structure settings, not on entry/exit settings,
    so optimisation trials that only change exits reuse it. Keyed on the data's identity + bounds + settings.
    Analyses are never mutated by strategies (zone state is fixed when built), so sharing is safe."""
    key = (len(df), df.index[0], df.index[-1], float(df["close"].iat[-1]), float(df["close"].sum()),
           tuple(sorted(kw.items())))
    a = _CACHE.get(key)
    if a is None:
        a = analyze_all(df, **kw)
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = a
    return a


DEFAULTS = {
    "swing_n": 3, "displacement_k": 1.5, "fvg_min_atr": 0.3, "sweep_bars": 3, "htf": "H4",
    "rr": 2.0, "min_rr": 2.0, "sl_buffer_atr": 0.2, "expires_bars": 20,
}


class StructureStrategy(Strategy):
    def p(self, key):
        return self.params.get(key, self.defaults.get(key, DEFAULTS.get(key)))

    defaults: dict = {}

    def on_start(self, ctx):
        df = ctx.df
        self.o, self.h, self.l, self.c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
        self.a: Analysis = cached_analysis(
            df, swing_n=self.p("swing_n"), displacement_k=self.p("displacement_k"), fvg_min_atr=self.p("fvg_min_atr"),
            sweep_bars=self.p("sweep_bars"), htf=self.p("htf") or None,
        )
        self.atr = self.a.atr
        self.zones_by_break: dict[int, Zone] = {z.source_break: z for z in self.a.ms.zones
                                                if z.kind == "OB" and z.source_break is not None}
        self.levels_at = [[] for _ in range(len(df))]
        for lv in self.a.levels:
            if lv.created_i < len(df):
                self.levels_at[lv.created_i].append(lv)
        self.pd_high = self.pd_low = np.nan  # latest previous-day high/low known so far
        self.last_sweep: dict[int, object] = {}

    # ---- per-bar bookkeeping every subclass wants ----
    def observe(self, i: int) -> None:
        for lv in self.levels_at[i]:
            if lv.kind == "PDH":
                self.pd_high = lv.price
            elif lv.kind == "PDL":
                self.pd_low = lv.price
        for s in self.a.sweeps_at[i]:
            self.last_sweep[s.direction] = s

    def breaks_now(self, i: int) -> list[tuple[int, Break]]:
        return [(bi, self.a.ms.breaks[bi]) for bi in self.a.ms.breaks_at[i]]

    def entry_zone(self, bi: int, b: Break, i: int, prefer: str = "ob") -> Zone | None:
        """OB created by this break, else the latest FVG in the break direction formed during the leg."""
        ob = self.zones_by_break.get(bi)
        fvg = None
        for j in range(i, b.leg_i - 1, -1):
            hits = [z for z in self.a.fvgs_at[j] if z.direction == b.direction]
            if hits:
                fvg = hits[-1]
                break
        first, second = (ob, fvg) if prefer == "ob" else (fvg, ob)
        return first or second

    def target(self, side: int, entry: float, risk: float, i: int) -> float | None:
        """Nearest opposite liquidity (last swing high/low, previous-day high/low) giving at least min_rr;
        otherwise a fixed min_rr target."""
        min_rr = self.p("min_rr")
        cands = [self.a.ms.last_high[i], self.pd_high] if side > 0 else [self.a.ms.last_low[i], self.pd_low]
        ok = [x for x in cands if not np.isnan(x) and (x - entry) * side >= min_rr * risk]
        if ok:
            return min(ok, key=lambda x: abs(x - entry))
        return entry + side * min_rr * risk

    def order(self, side: int, entry: float | None, sl: float, tp: float, reason: str, expires: int | None = None
              ) -> list[Signal]:
        ref = entry if entry is not None else self.c[self._i]
        if (ref - sl) * side <= 0 or (tp - ref) * side <= 0:
            return []
        return [Signal(self._sym, Side.BUY if side > 0 else Side.SELL, entry, sl, tp, self.name, reason,
                       expires_bars=expires if expires is not None else self.p("expires_bars"))]

    def bind(self, ctx) -> int:
        self._i, self._sym = ctx.i, ctx.instrument.symbol
        return ctx.i
