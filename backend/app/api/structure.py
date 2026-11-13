"""Chart Lab (doc 21, Phase 2): run the structure library on stored candles and return drawable overlays."""
from __future__ import annotations

from datetime import datetime, time

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app.backtest import runner
from app.data import pipeline as P
from app.structure import analyze_all, in_ny_window

router = APIRouter(prefix="/structure", tags=["structure"])

WARMUP = 400  # extra bars analysed before the window so swings/zones/levels already exist at its start
WINDOWS = {  # New York local time (doc 8.3)
    "Asia": (time(20, 0), time(0, 0)), "London KZ": (time(2, 0), time(5, 0)), "NY AM KZ": (time(7, 0), time(10, 0)),
    "Silver Bullet": (time(10, 0), time(11, 0)),
}
LEVEL_KINDS = {"PDH", "PDL", "PWH", "PWL", "ASIA_H", "ASIA_L", "EQH", "EQL"}


def _spans(idx: pd.DatetimeIndex, mask: np.ndarray) -> list[tuple[int, int]]:
    """[start, end] bar-index runs where mask is True."""
    out, start = [], None
    for i, m in enumerate(mask):
        if m and start is None:
            start = i
        if not m and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(mask) - 1))
    return out


@router.get("")
def structure(symbol: str = "EURUSD", timeframe: str = "M15", end: datetime | None = None,
              bars: int = Query(600, ge=100, le=3000), swing_n: int = Query(3, ge=1, le=10),
              displacement_k: float = Query(1.5, gt=0, le=5), fvg_min_atr: float = Query(0.3, ge=0, le=3)) -> dict:
    try:
        df = P.read_store(runner.DATA_ROOT, symbol, timeframe)
    except FileNotFoundError as e:
        raise HTTPException(404, f"No downloaded {timeframe} data for {symbol}") from e
    if end is not None:
        e = pd.Timestamp(end)
        df = df[df.index <= (e.tz_convert("UTC") if e.tzinfo else e.tz_localize("UTC"))]
    df = df.iloc[-(bars + WARMUP):]
    if len(df) < 50:
        raise HTTPException(404, "not enough candles before that date")
    a = analyze_all(df, swing_n=swing_n, displacement_k=displacement_k, fvg_min_atr=fvg_min_atr,
                    htf="H4" if timeframe in ("M1", "M5", "M15", "M30", "H1") else None)
    first = max(0, len(df) - bars)
    last = len(df) - 1
    t = df.index.as_unit("s").asi8.tolist()  # unix seconds per bar

    def vis(j: int | None) -> bool:
        return j is not None and j >= first

    def end_of(*idx: int | None) -> int:
        alive = [j for j in idx if j is not None]
        return min(min(alive), last) if alive else last

    zones = [
        {"kind": z.kind, "dir": z.direction, "top": z.top, "bottom": z.bottom,
         "from": t[max(z.origin_i, first)], "to": t[end_of(z.invalidated_i, z.filled_i, z.expires_i)],
         "mitigated": t[z.mitigated_i] if z.mitigated_i is not None and z.mitigated_i <= last else None,
         "state": "invalidated" if z.invalidated_i is not None and z.invalidated_i <= last
         else "filled" if z.filled_i is not None and z.filled_i <= last
         else "mitigated" if z.mitigated_i is not None and z.mitigated_i <= last else "fresh"}
        for z in [*a.ms.zones, *a.fvgs]
        if end_of(z.invalidated_i, z.filled_i, z.expires_i) >= first and z.created_i <= last
    ]
    swept_at = {id(s.level): s.i for s in a.sweeps}
    return {
        "symbol": symbol, "timeframe": timeframe,
        "candles": [{"time": t[i], "open": float(r.open), "high": float(r.high), "low": float(r.low), "close": float(r.close)}
                    for i, r in enumerate(df.itertuples(index=False)) if i >= first],
        "swings": [{"time": t[s.i], "price": s.price, "kind": s.kind, "confirmed": t[s.conf_i]}
                   for s in a.ms.swings if vis(s.i) and s.conf_i <= last],
        "breaks": [{"time": t[b.i], "from": t[max(b.swing_i, first)], "level": b.level, "kind": b.kind, "dir": b.direction,
                    "displacement": b.displacement} for b in a.ms.breaks if vis(b.i)],
        "zones": zones,
        "levels": [{"kind": lv.kind, "side": lv.side, "price": lv.price, "from": t[max(lv.created_i, first)],
                    "to": t[end_of(swept_at.get(id(lv)), lv.expires_i)]}
                   for lv in a.levels if lv.kind in LEVEL_KINDS and lv.created_i <= last
                   and end_of(swept_at.get(id(lv)), lv.expires_i) >= first],
        "sweeps": [{"time": t[s.i], "kind": s.level.kind, "dir": s.direction, "level": s.level.price, "extreme": s.extreme}
                   for s in a.sweeps if vis(s.i) and s.level.kind in LEVEL_KINDS | {"SWING_H", "SWING_L"}],
        "sessions": [{"name": name, "from": t[s], "to": t[e]}
                     for name, (ws, we) in WINDOWS.items()
                     for s, e in _spans(df.index, in_ny_window(df.index, ws, we)) if e >= first and s >= first - 50
                     for s in [max(s, first)]] if timeframe in ("M1", "M5", "M15", "M30", "H1") else [],
        "trend": int(a.ms.trend[last]), "htf": int(a.htf[last]),
        "range_pos": None if np.isnan(a.range_pos[last]) else round(float(a.range_pos[last]), 3),
    }
