from __future__ import annotations

import pandas as pd

from app.domain import Bar, Side, Signal
from app.indicators.core import adx, atr, ema
from app.patterns.candles import (
    bearish_engulfing,
    bearish_pin_bar,
    bullish_engulfing,
    bullish_pin_bar,
)
from app.strategies.base import Strategy


class EMATrendPullback(Strategy):
    """EMA-1 (doc 8.4): trend filter + pullback to EMA20/50 + confirmation candle."""

    name = "EMA-1"

    def on_start(self, ctx):
        p, df = self.params, ctx.df
        self.rr = p.get("rr", 2.0)
        self.atr_mult = p.get("atr_mult", 1.5)
        self.f20, self.f50, self.f200 = ema(df.close, 20), ema(df.close, 50), ema(df.close, 200)
        self.atr = atr(df)
        self.bull = bullish_engulfing(df) | bullish_pin_bar(df)
        self.bear = bearish_engulfing(df) | bearish_pin_bar(df)

    def on_bar(self, ctx, bar: Bar) -> list[Signal]:
        i = ctx.i
        a = self.atr.iat[i]
        if pd.isna(a) or pd.isna(self.f200.iat[i]):
            return []
        c = bar.close
        if c > self.f200.iat[i] and self.f20.iat[i] > self.f50.iat[i] and self.bull.iat[i] \
                and bar.low <= self.f20.iat[i]:  # pullback touched EMA20
            sl = c - self.atr_mult * a
            return [Signal(ctx.instrument.symbol, Side.BUY, None, sl, c + self.rr * (c - sl), self.name)]
        if c < self.f200.iat[i] and self.f20.iat[i] < self.f50.iat[i] and self.bear.iat[i] \
                and bar.high >= self.f20.iat[i]:
            sl = c + self.atr_mult * a
            return [Signal(ctx.instrument.symbol, Side.SELL, None, sl, c - self.rr * (sl - c), self.name)]
        return []


class EMACrossover(Strategy):
    """EMA-2 (doc 8.4): fast/slow cross, ADX filter, ATR stop, fixed RR."""

    name = "EMA-2"

    def on_start(self, ctx):
        p, df = self.params, ctx.df
        self.rr = p.get("rr", 2.0)
        self.atr_mult = p.get("atr_mult", 2.0)
        self.adx_min = p.get("adx_min", 20)
        self.fast = ema(df.close, p.get("fast", 20))
        self.slow = ema(df.close, p.get("slow", 50))
        self.atr = atr(df)
        self.adx = adx(df)

    def on_bar(self, ctx, bar: Bar) -> list[Signal]:
        i = ctx.i
        if i < 1 or pd.isna(self.slow.iat[i - 1]) or pd.isna(self.adx.iat[i]):
            return []
        if self.adx.iat[i] < self.adx_min:
            return []
        up = self.fast.iat[i - 1] <= self.slow.iat[i - 1] and self.fast.iat[i] > self.slow.iat[i]
        dn = self.fast.iat[i - 1] >= self.slow.iat[i - 1] and self.fast.iat[i] < self.slow.iat[i]
        a, c = self.atr.iat[i], bar.close
        if up:
            sl = c - self.atr_mult * a
            return [Signal(ctx.instrument.symbol, Side.BUY, None, sl, c + self.rr * (c - sl), self.name)]
        if dn:
            sl = c + self.atr_mult * a
            return [Signal(ctx.instrument.symbol, Side.SELL, None, sl, c - self.rr * (sl - c), self.name)]
        return []
