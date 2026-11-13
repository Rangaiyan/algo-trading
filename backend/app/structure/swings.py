"""Swing highs/lows (doc 8.1). A pivot at bar p is only KNOWN at bar p + n (after n bars close): no repainting."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Swing:
    i: int          # pivot bar index
    conf_i: int     # bar index at which the pivot is confirmed (i + n); usable from this bar on
    price: float
    kind: str       # "high" | "low"


def swings(df: pd.DataFrame, n: int = 3) -> list[Swing]:
    """Pivot = strictly highest high (lowest low) of the n bars each side; the first of equal highs wins.

    Returned in confirmation order (conf_i ascending), highs before lows on the same bar.
    """
    h, lo = df["high"].to_numpy(), df["low"].to_numpy()
    out: list[Swing] = []
    for p in range(n, len(df) - n):
        left_h, right_h = h[p - n:p], h[p + 1:p + n + 1]
        if h[p] > left_h.max() and h[p] >= right_h.max():  # strict on the left: the first of equal highs wins
            out.append(Swing(p, p + n, float(h[p]), "high"))
        left_l, right_l = lo[p - n:p], lo[p + 1:p + n + 1]
        if lo[p] < left_l.min() and lo[p] <= right_l.min():
            out.append(Swing(p, p + n, float(lo[p]), "low"))
    return out


def by_confirmation(sw: list[Swing], length: int) -> list[list[Swing]]:
    """Bucket swings by the bar at which they become known."""
    out: list[list[Swing]] = [[] for _ in range(length)]
    for s in sw:
        if s.conf_i < length:
            out[s.conf_i].append(s)
    return out


def last_swing_arrays(sw: list[Swing], length: int) -> tuple[np.ndarray, np.ndarray]:
    """Per bar: price of the most recent CONFIRMED swing high / low (NaN until one exists)."""
    hi, lo = np.full(length, np.nan), np.full(length, np.nan)
    for s in sw:
        if s.conf_i < length:
            (hi if s.kind == "high" else lo)[s.conf_i] = s.price
    return pd.Series(hi).ffill().to_numpy(), pd.Series(lo).ffill().to_numpy()
