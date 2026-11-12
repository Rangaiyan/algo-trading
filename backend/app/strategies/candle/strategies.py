from __future__ import annotations

import pandas as pd

from app.domain import Bar, Side, Signal
from app.indicators.core import atr, ema
from app.patterns.candles import (
    bearish_engulfing,
    bearish_pin_bar,
    bullish_engulfing,
    bullish_pin_bar,
)
from app.strategies.base import Strategy


class CandlestickBaseline(Strategy):
    """Standalone baseline (doc 8.5): pattern + EMA trend filter, SL beyond the pattern, fixed RR."""

    name = "CANDLE-1"

    def on_start(self, ctx):
        df = ctx.df
        self.rr = self.params.get("rr", 2.0)
        self.buf = self.params.get("sl_buffer_atr", 0.2)
        self.trend = ema(df.close, self.params.get("trend_ema", 200))
        self.atr = atr(df)
        self.bull = bullish_engulfing(df) | bullish_pin_bar(df)
        self.bear = bearish_engulfing(df) | bearish_pin_bar(df)

    def on_bar(self, ctx, bar: Bar) -> list[Signal]:
        i = ctx.i
        a, t = self.atr.iat[i], self.trend.iat[i]
        if pd.isna(a) or pd.isna(t):
            return []
        c = bar.close
        if self.bull.iat[i] and c > t:
            sl = bar.low - self.buf * a
            return [Signal(ctx.instrument.symbol, Side.BUY, None, sl, c + self.rr * (c - sl), self.name)]
        if self.bear.iat[i] and c < t:
            sl = bar.high + self.buf * a
            return [Signal(ctx.instrument.symbol, Side.SELL, None, sl, c - self.rr * (sl - c), self.name)]
        return []
