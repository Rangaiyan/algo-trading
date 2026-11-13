"""Candlestick detectors on CLOSED candles (doc 8.5). Vectorised and causal (use shift only)."""
from __future__ import annotations

import pandas as pd

from app.indicators.core import atr


def bullish_engulfing(df: pd.DataFrame, min_body_atr: float = 0.5) -> pd.Series:
    body = (df.close - df.open).abs()
    prev_bear = df.close.shift(1) < df.open.shift(1)
    return (prev_bear & (df.close > df.open) & (df.close >= df.open.shift(1))
            & (df.open <= df.close.shift(1)) & (body >= min_body_atr * atr(df))).fillna(False)


def bearish_engulfing(df: pd.DataFrame, min_body_atr: float = 0.5) -> pd.Series:
    body = (df.close - df.open).abs()
    prev_bull = df.close.shift(1) > df.open.shift(1)
    return (prev_bull & (df.close < df.open) & (df.close <= df.open.shift(1))
            & (df.open >= df.close.shift(1)) & (body >= min_body_atr * atr(df))).fillna(False)


def _parts(df):
    body = (df.close - df.open).abs()
    rng = (df.high - df.low).replace(0, float("nan"))
    upper = df.high - df[["open", "close"]].max(axis=1)
    lower = df[["open", "close"]].min(axis=1) - df.low
    return body, rng, upper, lower


def bullish_pin_bar(df: pd.DataFrame, wick_ratio: float = 2.0, min_range_atr: float = 0.8) -> pd.Series:
    body, rng, upper, lower = _parts(df)
    return ((lower >= wick_ratio * body) & (lower >= 0.6 * rng) & (upper <= 0.25 * rng)
            & (rng >= min_range_atr * atr(df))).fillna(False)


def bearish_pin_bar(df: pd.DataFrame, wick_ratio: float = 2.0, min_range_atr: float = 0.8) -> pd.Series:
    body, rng, upper, lower = _parts(df)
    return ((upper >= wick_ratio * body) & (upper >= 0.6 * rng) & (lower <= 0.25 * rng)
            & (rng >= min_range_atr * atr(df))).fillna(False)


def inside_bar(df: pd.DataFrame) -> pd.Series:
    return ((df.high < df.high.shift(1)) & (df.low > df.low.shift(1))).fillna(False)


def _bull(df, k=0):
    return df.close.shift(k) > df.open.shift(k)


def _bear(df, k=0):
    return df.close.shift(k) < df.open.shift(k)


def doji(df: pd.DataFrame, body_ratio: float = 0.1, min_range_atr: float = 0.3) -> pd.Series:
    """Body is a tiny fraction of the range: indecision (meaningful only at a level)."""
    body, rng, _, _ = _parts(df)
    return ((body <= body_ratio * rng) & (rng >= min_range_atr * atr(df))).fillna(False)


def morning_star(df: pd.DataFrame, small_body: float = 0.3, min_body_atr: float = 0.5) -> pd.Series:
    """Big bear, small-bodied middle candle, then a bull closing above the first candle's midpoint."""
    body, rng, _, _ = _parts(df)
    a = atr(df)
    first_mid = (df.open.shift(2) + df.close.shift(2)) / 2
    return (_bear(df, 2) & (body.shift(2) >= min_body_atr * a.shift(2))
            & (body.shift(1) <= small_body * body.shift(2))
            & _bull(df) & (body >= min_body_atr * a) & (df.close > first_mid)).fillna(False)


def evening_star(df: pd.DataFrame, small_body: float = 0.3, min_body_atr: float = 0.5) -> pd.Series:
    """Big bull, small-bodied middle candle, then a bear closing below the first candle's midpoint."""
    body, rng, _, _ = _parts(df)
    a = atr(df)
    first_mid = (df.open.shift(2) + df.close.shift(2)) / 2
    return (_bull(df, 2) & (body.shift(2) >= min_body_atr * a.shift(2))
            & (body.shift(1) <= small_body * body.shift(2))
            & _bear(df) & (body >= min_body_atr * a) & (df.close < first_mid)).fillna(False)


def tweezer_bottom(df: pd.DataFrame, tol_atr: float = 0.05) -> pd.Series:
    """Two candles with (nearly) equal lows, bear then bull."""
    return (_bear(df, 1) & _bull(df) & ((df.low - df.low.shift(1)).abs() <= tol_atr * atr(df))).fillna(False)


def tweezer_top(df: pd.DataFrame, tol_atr: float = 0.05) -> pd.Series:
    """Two candles with (nearly) equal highs, bull then bear."""
    return (_bull(df, 1) & _bear(df) & ((df.high - df.high.shift(1)).abs() <= tol_atr * atr(df))).fillna(False)


def three_white_soldiers(df: pd.DataFrame, min_body_atr: float = 0.4) -> pd.Series:
    """Three bull candles, each closing higher, each with a real body."""
    body = (df.close - df.open).abs()
    big = body >= min_body_atr * atr(df)
    return (_bull(df) & _bull(df, 1) & _bull(df, 2) & big & big.shift(1, fill_value=False) & big.shift(2, fill_value=False)
            & (df.close > df.close.shift(1)) & (df.close.shift(1) > df.close.shift(2))).fillna(False)


def three_black_crows(df: pd.DataFrame, min_body_atr: float = 0.4) -> pd.Series:
    """Three bear candles, each closing lower, each with a real body."""
    body = (df.close - df.open).abs()
    big = body >= min_body_atr * atr(df)
    return (_bear(df) & _bear(df, 1) & _bear(df, 2) & big & big.shift(1, fill_value=False) & big.shift(2, fill_value=False)
            & (df.close < df.close.shift(1)) & (df.close.shift(1) < df.close.shift(2))).fillna(False)


def inside_bar_breakout(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """(bullish, bearish): this candle closes beyond the mother bar of an inside bar one candle earlier."""
    ib = inside_bar(df).shift(1, fill_value=False)
    mother_high, mother_low = df.high.shift(2), df.low.shift(2)
    return (ib & (df.close > mother_high)).fillna(False), (ib & (df.close < mother_low)).fillna(False)


BULLISH = {
    "engulfing": bullish_engulfing, "pin_bar": bullish_pin_bar, "star": morning_star,
    "tweezer": tweezer_bottom, "three_candles": three_white_soldiers,
    "inside_breakout": lambda df: inside_bar_breakout(df)[0],
}
BEARISH = {
    "engulfing": bearish_engulfing, "pin_bar": bearish_pin_bar, "star": evening_star,
    "tweezer": tweezer_top, "three_candles": three_black_crows,
    "inside_breakout": lambda df: inside_bar_breakout(df)[1],
}
