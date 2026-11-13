"""Liquidity (doc 8.1): pools (previous day/week high-low, Asia range, swing and equal highs/lows) and sweeps.

A sweep = price trades beyond a level and a candle CLOSES back inside within `m` bars; the sweep is known at
that closing bar. A level that is closed beyond for longer than `m` bars is simply "taken" (no sweep).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time

import numpy as np
import pandas as pd

from app.structure.swings import Swing

ROLL_HOUR_NY = 17  # FX trading day rolls at 17:00 New York


@dataclass
class Level:
    price: float
    side: str          # "high" (buy-side liquidity above) | "low" (sell-side below)
    created_i: int     # usable from this bar
    kind: str          # "PDH" "PDL" "PWH" "PWL" "ASIA_H" "ASIA_L" "SWING_H" "SWING_L" "EQH" "EQL"
    expires_i: int


@dataclass
class Sweep:
    i: int             # bar that CLOSED back inside (sweep known here)
    break_i: int       # first bar that traded beyond the level
    level: Level
    extreme: float     # furthest price reached beyond the level

    @property
    def direction(self) -> int:
        """+1 = sell-side swept (bullish reversal setup), -1 = buy-side swept (bearish)."""
        return 1 if self.level.side == "low" else -1


def ny_index(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return index.tz_convert("America/New_York")


def trading_day(index: pd.DatetimeIndex) -> np.ndarray:
    """FX trading-day id per bar (day rolls at 17:00 New York), as numpy datetime64[D]."""
    ny = ny_index(index)
    return (ny + pd.Timedelta(hours=24 - ROLL_HOUR_NY)).tz_localize(None).normalize().to_numpy().astype("datetime64[D]")


def in_ny_window(index: pd.DatetimeIndex, start: time, end: time) -> np.ndarray:
    """Bars whose OPEN time falls in [start, end) New York time (windows may cross midnight)."""
    ny = ny_index(index)
    m = ny.hour * 60 + ny.minute
    s, e = start.hour * 60 + start.minute, end.hour * 60 + end.minute
    return ((m >= s) & (m < e)) if s < e else ((m >= s) | (m < e))


def previous_period_levels(df: pd.DataFrame, period: str = "day", max_age: int = 2000) -> list[Level]:
    """Previous trading day (or week) high/low, created at the first bar of the next period."""
    day = trading_day(df.index)
    key = day if period == "day" else (day - ((day.view("int64") - 4) % 7)).astype("datetime64[D]")  # week key = Monday of the trading week
    h, lo = df["high"].to_numpy(), df["low"].to_numpy()
    out: list[Level] = []
    starts = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
    hk, lk = ("PDH", "PDL") if period == "day" else ("PWH", "PWL")
    for prev, cur in zip(starts[:-1], starts[1:], strict=False):
        out.append(Level(float(h[prev:cur].max()), "high", int(cur), hk, int(cur) + max_age))
        out.append(Level(float(lo[prev:cur].min()), "low", int(cur), lk, int(cur) + max_age))
    return out


def asia_levels(df: pd.DataFrame, start: time = time(20, 0), end: time = time(0, 0), max_age: int = 200
                ) -> tuple[list[Level], np.ndarray, np.ndarray]:
    """Asia range high/low per trading day, known from the first bar after the window ends.

    Also returns per-bar arrays (asia_high, asia_low) of the CURRENT trading day's completed range (NaN before).
    """
    inside = in_ny_window(df.index, start, end)
    day = trading_day(df.index)
    h, lo = df["high"].to_numpy(), df["low"].to_numpy()
    ah, al = np.full(len(df), np.nan), np.full(len(df), np.nan)
    out: list[Level] = []
    cur_day, hi, low, seen, done = None, -np.inf, np.inf, False, False
    for i in range(len(df)):
        if day[i] != cur_day:
            cur_day, hi, low, seen, done = day[i], -np.inf, np.inf, False, False
        if inside[i]:
            hi, low, seen = max(hi, h[i]), min(low, lo[i]), True
        elif seen and not done:
            done = True
            out.append(Level(float(hi), "high", i, "ASIA_H", i + max_age))
            out.append(Level(float(low), "low", i, "ASIA_L", i + max_age))
        if done:
            ah[i], al[i] = hi, low
    return out, ah, al


def swing_levels(sw: list[Swing], atr: np.ndarray, eq_tol: float = 0.1, lookback: int = 100, max_age: int = 300
                 ) -> list[Level]:
    """Every confirmed swing is a liquidity level; two swings within eq_tol x ATR form equal highs/lows."""
    out: list[Level] = []
    recent: dict[str, list[Swing]] = {"high": [], "low": []}
    for s in sorted(sw, key=lambda x: (x.conf_i, x.i)):
        side = s.kind
        out.append(Level(s.price, side, s.conf_i, "SWING_H" if side == "high" else "SWING_L", s.conf_i + max_age))
        a = atr[s.conf_i] if s.conf_i < len(atr) else np.nan
        if not np.isnan(a):
            for p in recent[side]:
                if s.i - p.i <= lookback and abs(s.price - p.price) <= eq_tol * a:
                    lvl = max(s.price, p.price) if side == "high" else min(s.price, p.price)
                    out.append(Level(lvl, side, s.conf_i, "EQH" if side == "high" else "EQL", s.conf_i + max_age))
                    break
        recent[side] = [p for p in recent[side] if s.i - p.i <= lookback] + [s]
    return out


def sweeps(df: pd.DataFrame, levels: list[Level], m: int = 3) -> list[Sweep]:
    """Forward pass: each level can be swept (or taken) once."""
    h, lo, c = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    pending = sorted(levels, key=lambda lv: lv.created_i)
    live: list[Level] = []
    beyond: dict[int, tuple[int, float]] = {}   # id(level) -> (first bar beyond, extreme)
    out: list[Sweep] = []
    k = 0
    for i in range(len(df)):
        while k < len(pending) and pending[k].created_i <= i:
            live.append(pending[k])
            k += 1
        keep: list[Level] = []
        for lv in live:
            if i >= lv.expires_i:
                continue
            up = lv.side == "high"
            pierced = h[i] > lv.price if up else lo[i] < lv.price
            key = id(lv)
            if key not in beyond and pierced and i > lv.created_i:
                beyond[key] = (i, h[i] if up else lo[i])
            if key in beyond:
                b_i, ext = beyond[key]
                ext = max(ext, h[i]) if up else min(ext, lo[i])
                beyond[key] = (b_i, ext)
                if (c[i] < lv.price) if up else (c[i] > lv.price):
                    out.append(Sweep(i, b_i, lv, float(ext)))
                    continue  # swept: level is used up
                if i - b_i >= m:
                    continue  # stayed beyond: taken, not swept
            keep.append(lv)
        live = keep
    return out
