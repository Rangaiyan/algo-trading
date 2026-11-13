"""Market-structure library for SMC / ICT (doc 8.1). Everything is causal: an object is usable from the bar
index it records (conf_i / created_i / i) and never changes when later bars are appended."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time

import numpy as np
import pandas as pd

from app.structure.context import htf_trend, range_position
from app.structure.fvg import fvgs
from app.structure.liquidity import (
    Level, Sweep, asia_levels, in_ny_window, previous_period_levels, swing_levels, sweeps, trading_day,
)
from app.structure.market import Break, Structure, Zone, analyze
from app.structure.swings import Swing

__all__ = ["Analysis", "Break", "Level", "Sweep", "Swing", "Zone", "analyze_all", "in_ny_window", "trading_day"]


@dataclass
class Analysis:
    ms: Structure
    fvgs: list[Zone]
    levels: list[Level]
    sweeps: list[Sweep]
    asia_high: np.ndarray
    asia_low: np.ndarray
    range_pos: np.ndarray       # premium (> 0.5) / discount (< 0.5) of the current dealing range
    htf: np.ndarray             # higher-timeframe trend per bar (0 when disabled)
    sweeps_at: list[list[Sweep]] = field(default_factory=list)
    fvgs_at: list[list[Zone]] = field(default_factory=list)

    @property
    def atr(self) -> np.ndarray:
        return self.ms.atr


def analyze_all(df: pd.DataFrame, swing_n: int = 3, displacement_k: float = 1.5, fvg_min_atr: float = 0.3,
                sweep_bars: int = 3, eq_tol: float = 0.1, htf: str | None = "H4", ob_zone: str = "body",
                asia: tuple[time, time] = (time(20, 0), time(0, 0))) -> Analysis:
    ms = analyze(df, n=swing_n, displacement_k=displacement_k, ob_zone=ob_zone)
    gaps = fvgs(df, min_atr=fvg_min_atr, a=ms.atr)
    asia_lv, ah, al = asia_levels(df, *asia)
    levels = (previous_period_levels(df, "day") + previous_period_levels(df, "week") + asia_lv
              + swing_levels(ms.swings, ms.atr, eq_tol))
    sw = sweeps(df, levels, m=sweep_bars)
    n = len(df)
    sweeps_at: list[list[Sweep]] = [[] for _ in range(n)]
    for s in sw:
        sweeps_at[s.i].append(s)
    fvgs_at: list[list[Zone]] = [[] for _ in range(n)]
    for z in gaps:
        fvgs_at[z.created_i].append(z)
    return Analysis(
        ms=ms, fvgs=gaps, levels=levels, sweeps=sw, asia_high=ah, asia_low=al,
        range_pos=range_position(df["close"].to_numpy(), ms.last_high, ms.last_low),
        htf=htf_trend(df, htf, n=swing_n) if htf else np.zeros(n, dtype=int),
        sweeps_at=sweeps_at, fvgs_at=fvgs_at,
    )
