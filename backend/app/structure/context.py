"""Context filters (doc 8.1): premium/discount of the dealing range and higher-timeframe bias."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.data.pipeline import TF_RULES
from app.structure.market import analyze


def range_position(close: np.ndarray, last_high: np.ndarray, last_low: np.ndarray) -> np.ndarray:
    """0 = at the dealing-range low, 1 = at its high, 0.5 = equilibrium. NaN when no valid range."""
    span = last_high - last_low
    with np.errstate(invalid="ignore", divide="ignore"):
        pos = (close - last_low) / span
    pos[~(span > 0)] = np.nan
    return pos


def htf_trend(df: pd.DataFrame, htf: str = "H4", n: int = 3) -> np.ndarray:
    """Higher-timeframe structure trend mapped onto each lower-timeframe bar, using only CLOSED HTF bars.

    An HTF bar [t, t+D) is usable by the LTF bar whose close time (ts + ltf) is >= t + D.
    """
    rule = TF_RULES[htf]
    agg = df.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "spread": "mean"}
    ).dropna(subset=["open"])
    if len(agg) < 2 * n + 2:
        return np.zeros(len(df), dtype=int)
    t = analyze(agg, n=n).trend
    htf_close = agg.index + pd.Timedelta(rule)
    ltf = df.index.to_series().diff().median() if len(df) > 1 else pd.Timedelta(0)
    ltf_close = df.index + ltf
    pos = np.searchsorted(htf_close.as_unit("ns").asi8, ltf_close.as_unit("ns").asi8, side="right") - 1  # last closed HTF bar
    out = np.zeros(len(df), dtype=int)
    ok = pos >= 0
    out[ok] = t[pos[ok]]
    return out
