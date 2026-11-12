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
