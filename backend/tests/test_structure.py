"""Phase 2 structure library: building blocks on hand-made candles, plus the non-repainting guarantee."""
from dataclasses import asdict
from datetime import time

import numpy as np
import pandas as pd
import pytest

from app.backtest.engine import BacktestConfig, run_backtest
from app.data import pipeline as P
from app.domain import Bar, Instrument, Market, Side, Signal
from app.strategies.base import Strategy
from app.structure import analyze_all
from app.structure.context import htf_trend
from app.structure.fvg import fvgs
from app.structure.liquidity import Level, asia_levels, in_ny_window, previous_period_levels, sweeps, trading_day
from app.structure.market import analyze
from app.structure.swings import swings


def frame(closes, start="2026-03-02 00:00", freq="15min", wick=0.0002):
    """Candles from a close path: open = previous close, small wicks."""
    c = np.asarray(closes, dtype=float)
    o = np.r_[c[0], c[:-1]]
    idx = pd.date_range(start, periods=len(c), freq=freq, tz="UTC")
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + wick, "low": np.minimum(o, c) - wick,
                         "close": c, "volume": 1.0, "spread": 0.0}, index=idx)


# ---------------- building blocks ----------------

def test_swings_confirm_only_after_n_bars():
    df = frame([1.0, 1.1, 1.2, 1.3, 1.2, 1.1, 1.0, 1.1, 1.2])
    sw = swings(df, n=3)
    hi = [s for s in sw if s.kind == "high"]
    assert [(s.i, s.conf_i) for s in hi] == [(3, 6)]
    assert swings(df.iloc[:6], n=3) == []  # bar 6 not closed yet -> pivot unknown


def test_bos_then_choch():
    # up-swing high at 1.3, pull back, close above it (BOS up); later close below the swing low (CHoCH down)
    path = [1.0, 1.1, 1.2, 1.3, 1.2, 1.1, 1.0, 1.1, 1.2, 1.35, 1.4, 1.3, 1.2, 1.1, 0.9, 0.8]
    ms = analyze(frame(path, wick=0.0), n=3)
    kinds = [(b.kind, b.direction) for b in ms.breaks]
    assert kinds[0] == ("BOS", 1) and ("CHoCH", -1) in kinds
    b = ms.breaks[0]
    assert b.level == pytest.approx(1.3) and b.leg_price == pytest.approx(1.0) and b.i == 9
    assert ms.trend[b.i] == 1 and ms.trend[b.i - 1] == 0


def test_order_block_is_last_opposite_candle_before_the_leg():
    path = [1.0, 1.1, 1.2, 1.3, 1.2, 1.1, 1.0, 1.1, 1.2, 1.35]
    ms = analyze(frame(path, wick=0.0), n=3)
    ob = next(z for z in ms.zones if z.kind == "OB")
    assert ob.direction == 1 and ob.origin_i == 6 and (ob.bottom, ob.top) == pytest.approx((1.0, 1.1))
    assert ob.created_i == 9


def test_fvg_detect_and_fill():
    df = frame([1.0, 1.0, 1.0, 1.01, 1.03, 1.05, 1.03, 1.0, 0.99], wick=0.0)
    # bar 4: low 1.01 > bar 2 high 1.0 -> bullish gap 1.00..1.01
    z = next(z for z in fvgs(df, min_atr=0.0) if z.direction == 1)
    assert z.created_i == 4 and (z.bottom, z.top) == pytest.approx((1.0, 1.01))
    assert z.mitigated_i == 7 and z.filled_i == 7 and z.invalidated_i == 8


def test_sweep_needs_close_back_inside_within_m_bars():
    df = frame([1.10, 1.10, 1.10, 1.10, 1.10, 1.10], wick=0.0)
    df.loc[df.index[2], "low"] = 1.08            # wick below 1.09 ...
    lv = Level(1.09, "low", 1, "PDL", 999)
    s = sweeps(df, [lv], m=3)
    assert len(s) == 1 and s[0].i == 2 and s[0].direction == 1 and s[0].extreme == pytest.approx(1.08)
    taken = frame([1.10, 1.08, 1.07, 1.07, 1.07, 1.07, 1.10], wick=0.0)  # closes below for > m bars
    assert sweeps(taken, [Level(1.09, "low", 0, "PDL", 999)], m=3) == []


def test_ny_windows_and_trading_day_follow_dst():
    # 2026-03-09: US already on DST (EDT, UTC-4); London not yet.  07:00 UTC = 03:00 NY
    idx = pd.DatetimeIndex(["2026-03-09 06:45", "2026-03-09 07:00", "2026-03-09 20:59", "2026-03-09 21:00"], tz="UTC")
    assert list(in_ny_window(idx, time(3), time(4))) == [False, True, False, False]
    td = trading_day(idx)
    assert td[2] == np.datetime64("2026-03-09") and td[3] == np.datetime64("2026-03-10")  # 17:00 NY roll


def test_asia_range_known_only_after_window():
    idx = pd.date_range("2026-03-10 00:00", "2026-03-10 06:00", freq="1h", tz="UTC")  # 20:00..02:00 NY (EDT)
    df = pd.DataFrame({"open": 1.0, "high": np.arange(len(idx)) * 0.001 + 1.01, "low": 0.99, "close": 1.0,
                       "volume": 1.0, "spread": 0.0}, index=idx)
    lv, ah, al = asia_levels(df)
    assert [lvl.kind for lvl in lv] == ["ASIA_H", "ASIA_L"] and lv[0].created_i == 4  # 00:00 NY bar
    assert np.isnan(ah[:4]).all() and ah[4] == pytest.approx(1.013)


def test_previous_day_levels_created_at_roll():
    idx = pd.date_range("2026-03-09 18:00", "2026-03-10 23:00", freq="1h", tz="UTC")
    df = pd.DataFrame({"open": 1.0, "high": 1.01, "low": 0.99, "close": 1.0, "volume": 1.0, "spread": 0.0}, index=idx)
    lv = previous_period_levels(df, "day")
    assert {lvl.kind for lvl in lv} == {"PDH", "PDL"}
    assert df.index[lv[0].created_i] == pd.Timestamp("2026-03-09 21:00", tz="UTC")  # 17:00 NY


def test_htf_trend_uses_only_closed_htf_bars():
    df = P.synthetic(days=40)
    full = htf_trend(df, "H4")
    for k in (1500, 2222, 3001):
        assert (htf_trend(df.iloc[:k], "H4") == full[:k]).all()


# ---------------- no repainting ----------------

def _clip(obj: dict, k: int) -> dict:
    return {f: (None if f in ("mitigated_i", "filled_i", "invalidated_i") and v is not None and v >= k else v)
            for f, v in obj.items() if f != "meta"}


@pytest.mark.parametrize("k", [1200, 2500, 3777])
def test_analysis_never_repaints(k):
    df = P.synthetic(days=60)
    full, part = analyze_all(df), analyze_all(df.iloc[:k])
    assert [s for s in full.ms.swings if s.conf_i < k] == part.ms.swings
    assert [asdict(b) for b in full.ms.breaks if b.i < k] == [asdict(b) for b in part.ms.breaks]
    assert [_clip(asdict(z), k) for z in full.ms.zones if z.created_i < k] == [_clip(asdict(z), k) for z in part.ms.zones]
    assert [_clip(asdict(z), k) for z in full.fvgs if z.created_i < k] == [_clip(asdict(z), k) for z in part.fvgs]
    key = lambda s: (s.i, s.break_i, s.level.kind, s.level.price, s.extreme)  # noqa: E731
    assert [key(s) for s in full.sweeps if s.i < k] == [key(s) for s in part.sweeps]
    for name in ("trend", "last_high", "last_low"):
        np.testing.assert_array_equal(getattr(full.ms, name)[:k], getattr(part.ms, name))
    for name in ("range_pos", "htf", "asia_high", "asia_low"):
        np.testing.assert_array_equal(getattr(full, name)[:k], getattr(part, name))


# ---------------- limit orders in the engine ----------------

class _LimitOnce(Strategy):
    def on_bar(self, ctx, bar: Bar):
        if ctx.i == self.params["at"]:
            return [Signal("EURUSD", Side.BUY, self.params["entry"], self.params["sl"], self.params["tp"], "T",
                           expires_bars=self.params.get("exp", 5))]
        return []


def test_limit_order_fills_only_when_touched_and_expires():
    df = frame([1.10] * 5 + [1.105, 1.104, 1.099, 1.10, 1.11, 1.12, 1.13], wick=0.0)
    inst = Instrument(Market.FOREX, "EURUSD")
    r = run_backtest(df, _LimitOnce(at=4, entry=1.0995, sl=1.09, tp=1.12), inst, BacktestConfig())
    assert len(r.trades) == 1 and r.trades[0].entry_px == pytest.approx(1.0995)
    assert r.trades[0].entry_ts == df.index[7]  # first bar trading down to the limit
    never = run_backtest(df, _LimitOnce(at=4, entry=1.05, sl=1.04, tp=1.12, exp=3), inst, BacktestConfig())
    assert never.trades == []
