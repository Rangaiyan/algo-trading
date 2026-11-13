"""No-code rule builder (doc 9.2) with confluence scoring (doc 9.1).

A JSON spec is interpreted into the Strategy interface. Every candidate setup starts at a structure break
(BOS / CHoCH) on a closed candle; the blocks then decide whether to take it:
  mode "all":   every block must pass
  mode "score": sum the weights of passing blocks; trade when the sum >= threshold
Filters (sessions, max spread) always gate. Exits: stop beyond the sweep / zone / ATR; target fixed RR or the
next liquidity pool with a minimum RR.
"""
from __future__ import annotations

from datetime import time

import numpy as np

from app.domain import Bar, Signal
from app.indicators.core import ema
from app.patterns.candles import BEARISH, BULLISH
from app.strategies.structure_base import StructureStrategy
from app.structure import in_ny_window

BLOCKS = {
    "structure_break": "BOS / CHoCH on a candle close (the trigger). Options: kind any|BOS|CHoCH, displacement true|false",
    "liquidity_sweep": "A liquidity level was swept in the trade direction within N bars. Options: levels, within",
    "htf_bias": "Higher-timeframe (H4) structure agrees with the trade direction",
    "premium_discount": "Entry is in the discount half of the move (longs) / premium half (shorts)",
    "ema_trend": "Price and EMAs agree: close above slow EMA and fast > slow for longs. Options: fast, slow",
    "candle_confirm": "A confirmation candle pattern in the trade direction within the last 3 bars. Options: patterns",
    "session": "Setup forms inside one of the chosen New York windows. Options: sessions",
}
SESSIONS = {"asia": ("20:00", "00:00"), "london_kz": ("02:00", "05:00"), "ny_am_kz": ("07:00", "10:00"),
            "ny_pm": ("13:30", "16:00"), "silver_bullet_am": ("10:00", "11:00"), "silver_bullet_pm": ("14:00", "15:00")}
LEVEL_GROUPS = {"prev_day_hl": {"PDH", "PDL"}, "prev_week_hl": {"PWH", "PWL"}, "asia_hl": {"ASIA_H", "ASIA_L"},
                "equal_hl": {"EQH", "EQL"}, "swing_hl": {"SWING_H", "SWING_L"}}

EXAMPLE = {
    "name": "SMC sweep + CHoCH + FVG (London / NY)",
    "structure": {"swing_n": 3, "displacement_k": 1.5, "fvg_min_atr": 0.3},
    "filters": {"sessions": ["london_kz", "ny_am_kz"], "max_spread_pips": 2.0},
    "mode": "score", "threshold": 6,
    "setup": [
        {"block": "structure_break", "kind": "CHoCH", "displacement": True, "weight": 2},
        {"block": "liquidity_sweep", "levels": ["prev_day_hl", "asia_hl", "equal_hl"], "within": 30, "weight": 2},
        {"block": "htf_bias", "weight": 2},
        {"block": "premium_discount", "weight": 1},
        {"block": "ema_trend", "fast": 50, "slow": 200, "weight": 1},
        {"block": "candle_confirm", "patterns": ["engulfing", "pin_bar"], "weight": 1},
    ],
    "entry": {"type": "zone", "zone": ["fvg", "ob"], "at": "mid", "expires_bars": 20},
    "exit": {"stop": "sweep", "buffer_atr": 0.2, "take_profit": {"type": "next_liquidity", "min_rr": 2}},
}


def validate_spec(spec: dict) -> list[str]:
    errs = []
    if not isinstance(spec, dict):
        return ["spec must be a JSON object"]
    setup = spec.get("setup")
    if not isinstance(setup, list) or not setup:
        errs.append("setup must be a non-empty list of blocks")
        setup = []
    for k, b in enumerate(setup):
        if not isinstance(b, dict) or b.get("block") not in BLOCKS:
            errs.append(f"setup[{k}]: unknown block {b.get('block') if isinstance(b, dict) else b!r}; choose from {sorted(BLOCKS)}")
        elif b["block"] == "liquidity_sweep" and set(b.get("levels", [])) - set(LEVEL_GROUPS):
            errs.append(f"setup[{k}]: levels must be from {sorted(LEVEL_GROUPS)}")
        elif b["block"] == "candle_confirm" and set(b.get("patterns", [])) - set(BULLISH):
            errs.append(f"setup[{k}]: patterns must be from {sorted(BULLISH)}")
        elif b["block"] == "session" and set(b.get("sessions", [])) - set(SESSIONS):
            errs.append(f"setup[{k}]: sessions must be from {sorted(SESSIONS)}")
    if spec.get("mode", "all") not in ("all", "score"):
        errs.append("mode must be 'all' or 'score'")
    if spec.get("mode") == "score" and not isinstance(spec.get("threshold"), (int, float)):
        errs.append("score mode needs a numeric threshold")
    if set((spec.get("filters") or {}).get("sessions", [])) - set(SESSIONS):
        errs.append(f"filters.sessions must be from {sorted(SESSIONS)}")
    entry = spec.get("entry") or {}
    if entry.get("type", "zone") not in ("zone", "market"):
        errs.append("entry.type must be 'zone' or 'market'")
    ex = spec.get("exit") or {}
    if ex.get("stop", "zone") not in ("sweep", "zone", "atr"):
        errs.append("exit.stop must be 'sweep', 'zone' or 'atr'")
    if (ex.get("take_profit") or {}).get("type", "rr") not in ("rr", "next_liquidity"):
        errs.append("exit.take_profit.type must be 'rr' or 'next_liquidity'")
    return errs


def _win(sessions, idx):
    m = np.zeros(len(idx), dtype=bool)
    for name in sessions:
        s, e = SESSIONS[name]
        m |= in_ny_window(idx, time(*map(int, s.split(":"))), time(*map(int, e.split(":"))))
    return m


class RuleStrategy(StructureStrategy):
    """RULE (doc 9.2): a strategy defined as JSON blocks, with optional confluence scoring (doc 9.1)."""

    name = "RULE"

    def __init__(self, spec: dict | None = None, **params):
        import copy
        spec = copy.deepcopy(spec or EXAMPLE)
        # optimiser overrides on top of the saved spec
        if "threshold" in params:
            spec["threshold"] = params.pop("threshold")
        ex = spec.setdefault("exit", {})
        if "buffer_atr" in params:
            ex["buffer_atr"] = params.pop("buffer_atr")
        tp = ex.setdefault("take_profit", {"type": "rr", "rr": 2})
        for k in ("rr", "min_rr"):
            if k in params:
                tp[k] = params.pop(k)
        errs = validate_spec(spec)
        if errs:
            raise ValueError("; ".join(errs))
        st = spec.get("structure") or {}
        from_spec = {k: st[k] for k in ("swing_n", "displacement_k", "fvg_min_atr", "sweep_bars") if k in st}
        from_spec["htf"] = (spec.get("timeframes") or {}).get("bias", "H4")
        super().__init__(spec=spec, **{**from_spec, **params})  # explicit params (optimiser) override the spec
        self.spec = spec

    def on_start(self, ctx):
        super().on_start(ctx)
        df, sp = ctx.df, self.spec
        self.blocks = sp["setup"]
        self.trigger = next((b for b in self.blocks if b["block"] == "structure_break"), {"block": "structure_break", "weight": 0})
        self.filt = sp.get("filters") or {}
        self.filter_win = _win(self.filt["sessions"], df.index) if self.filt.get("sessions") else None
        self.spread = df["spread"].to_numpy() if "spread" in df else np.zeros(len(df))
        self.pip = ctx.instrument.pip_size
        self.cache = {}
        for b in self.blocks:
            if b["block"] == "ema_trend":
                f, s = b.get("fast", 50), b.get("slow", 200)
                self.cache[("ema", f, s)] = (ema(df.close, f).to_numpy(), ema(df.close, s).to_numpy())
            elif b["block"] == "candle_confirm":
                names = b.get("patterns", ["engulfing", "pin_bar"])
                bull = np.zeros(len(df), dtype=bool)
                bear = np.zeros(len(df), dtype=bool)
                for n in names:
                    bull |= BULLISH[n](df).to_numpy()
                    bear |= BEARISH[n](df).to_numpy()
                self.cache[("cc", tuple(names))] = (bull, bear)
            elif b["block"] == "session":
                self.cache[("sess", tuple(b.get("sessions", [])))] = _win(b.get("sessions", []), df.index)
        self.sweeps_by_dir: dict[int, list] = {1: [], -1: []}

    def _sweep(self, b, d, i):
        kinds = set().union(*(LEVEL_GROUPS[g] for g in b.get("levels", list(LEVEL_GROUPS))))
        within = b.get("within", 30)
        for s in reversed(self.sweeps_by_dir[d]):
            if i - s.i > within:
                return None
            if s.level.kind in kinds:
                return s
        return None

    def _passes(self, b, d, i, brk, entry) -> bool:
        k = b["block"]
        if k == "structure_break":
            return (b.get("kind", "any") in ("any", brk.kind)) and (not b.get("displacement") or brk.displacement)
        if k == "liquidity_sweep":
            return self._sweep(b, d, i) is not None
        if k == "htf_bias":
            return self.a.htf[i] == d
        if k == "premium_discount":
            lo, hi = (brk.leg_price, max(self.h[brk.leg_i:i + 1])) if d > 0 else (min(self.l[brk.leg_i:i + 1]), brk.leg_price)
            return hi > lo and ((entry - lo) / (hi - lo) - 0.5) * d <= 0
        if k == "ema_trend":
            f, s = self.cache[("ema", b.get("fast", 50), b.get("slow", 200))]
            return not np.isnan(s[i]) and (self.c[i] - s[i]) * d > 0 and (f[i] - s[i]) * d > 0
        if k == "candle_confirm":
            bull, bear = self.cache[("cc", tuple(b.get("patterns", ["engulfing", "pin_bar"])))]
            arr = bull if d > 0 else bear
            return bool(arr[max(0, i - 2):i + 1].any())
        if k == "session":
            return bool(self.cache[("sess", tuple(b.get("sessions", [])))][i])
        return False

    def on_bar(self, ctx, bar: Bar) -> list[Signal]:
        i = self.bind(ctx)
        self.observe(i)
        for s in self.a.sweeps_at[i]:
            self.sweeps_by_dir[s.direction].append(s)
        if self.filter_win is not None and not self.filter_win[i]:
            return []
        if self.filt.get("max_spread_pips") and self.spread[i] / self.pip > self.filt["max_spread_pips"]:
            return []
        sp, en, ex = self.spec, self.spec.get("entry") or {}, self.spec.get("exit") or {}
        for bi, brk in self.breaks_now(i):
            d = brk.direction
            if np.isnan(self.atr[i]) or not self._passes(self.trigger, d, i, brk, self.c[i]):
                continue
            zone = None
            if en.get("type", "zone") == "zone":
                kinds = en.get("zone", ["ob", "fvg"])
                zone = self.entry_zone(bi, brk, i, kinds[0])
                if zone is None or (zone.kind == "OB" and "ob" not in kinds) or (zone.kind == "FVG" and "fvg" not in kinds):
                    continue
                entry = zone.mid if en.get("at", "edge") == "mid" else (zone.top if d > 0 else zone.bottom)
            else:
                entry = self.c[i]
            passed = [b for b in self.blocks if self._passes(b, d, i, brk, entry)]
            if sp.get("mode", "all") == "all":
                if len(passed) < len(self.blocks):
                    continue
            elif sum(b.get("weight", 1) for b in passed) < sp["threshold"]:
                continue
            buf = ex.get("buffer_atr", 0.2) * self.atr[i]
            stop = ex.get("stop", "zone")
            sweep = self._sweep(next((b for b in self.blocks if b["block"] == "liquidity_sweep"), {}), d, i)
            if stop == "sweep" and sweep is not None:
                sl = sweep.extreme - d * buf
            elif stop in ("sweep", "zone") and zone is not None:
                sl = (zone.bottom if d > 0 else zone.top) - d * buf
            else:
                sl = entry - d * ex.get("atr_mult", 1.5) * self.atr[i]
            risk = abs(entry - sl)
            tp_spec = ex.get("take_profit") or {"type": "rr", "rr": 2}
            if tp_spec.get("type") == "next_liquidity":
                self.params["min_rr"] = tp_spec.get("min_rr", 2)
                tp = self.target(d, entry, risk, i)
            else:
                tp = entry + d * tp_spec.get("rr", 2) * risk
            score = sum(b.get("weight", 1) for b in passed)
            return self.order(d, None if en.get("type") == "market" else entry, sl, tp,
                              f"{brk.kind} score {score}: " + ", ".join(b["block"] for b in passed),
                              expires=en.get("expires_bars", 20))
        return []
