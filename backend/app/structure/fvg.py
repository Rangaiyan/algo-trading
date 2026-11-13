"""Fair Value Gaps (doc 8.1): 3-candle imbalance, known when the third candle closes; mitigation tracked forward."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.indicators.core import atr
from app.structure.market import Zone, track_all


def fvgs(df: pd.DataFrame, min_atr: float = 0.3, max_age: int = 500, a: np.ndarray | None = None) -> list[Zone]:
    """Bullish FVG at bar i: low[i] > high[i-2] (zone high[i-2]..low[i]); bearish: high[i] < low[i-2].

    Gaps smaller than `min_atr` x ATR are ignored. `mitigated_i` = first touch, `filled_i` = traded through,
    `invalidated_i` = closed through the far side.
    """
    h, lo, c = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    a = atr(df).to_numpy() if a is None else a
    out: list[Zone] = []
    live: list[Zone] = []
    for i in range(len(df)):
        track_all(live, i, h[i], lo[i], c[i], max_age)
        if i < 2:
            continue
        floor = min_atr * a[i] if min_atr else 0.0
        if np.isnan(floor):
            continue  # size filter needs ATR, which is not defined yet
        if lo[i] > h[i - 2] and lo[i] - h[i - 2] >= floor:
            z = Zone("FVG", 1, float(lo[i]), float(h[i - 2]), i, i - 1, expires_i=i + max_age)
        elif h[i] < lo[i - 2] and lo[i - 2] - h[i] >= floor:
            z = Zone("FVG", -1, float(lo[i - 2]), float(h[i]), i, i - 1, expires_i=i + max_age)
        else:
            continue
        out.append(z)
        live.append(z)
    return out
