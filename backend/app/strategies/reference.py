"""Gate 0 reference strategy (doc 10.3 week 1): deliberately simple, so MT5's Strategy Tester can run the exact same
rules (mt5-gateway/mql5/RinzGate0.mq5) and the two engines can be compared trade by trade.

Rules: on a CLOSED bar, buy when EMA(fast) crosses above EMA(slow) (sell on the opposite cross); market entry at the
next bar's open; fixed stop-loss / take-profit in pips; one position at a time; no other exit.
"""
from __future__ import annotations

import pandas as pd

from app.domain import Bar, Side, Signal
from app.indicators.core import ema
from app.strategies.base import Strategy


class Gate0Reference(Strategy):
    """GATE0: EMA cross with fixed-pip SL/TP (reference for the MT5 Strategy Tester cross-check)."""

    name = "GATE0"

    def on_start(self, ctx):
        p, df = self.params, ctx.df
        self.sl_pips, self.tp_pips = p.get("sl_pips", 30), p.get("tp_pips", 60)
        self.fast, self.slow = ema(df.close, p.get("fast", 20)), ema(df.close, p.get("slow", 50))
        tf = p.get("trade_from")
        self.trade_from = pd.Timestamp(tf) if tf else None

    def on_bar(self, ctx, bar: Bar) -> list[Signal]:
        i = ctx.i
        if i < 1 or pd.isna(self.slow.iat[i - 1]):
            return []
        if self.trade_from is not None and pd.Timestamp(bar.ts) < self.trade_from:
            return []
        f0, s0, f1, s1 = self.fast.iat[i - 1], self.slow.iat[i - 1], self.fast.iat[i], self.slow.iat[i]
        pip, c = ctx.instrument.pip_size, bar.close
        if f0 <= s0 and f1 > s1:
            return [Signal(ctx.instrument.symbol, Side.BUY, None, c - self.sl_pips * pip, c + self.tp_pips * pip, self.name)]
        if f0 >= s0 and f1 < s1:
            return [Signal(ctx.instrument.symbol, Side.SELL, None, c + self.sl_pips * pip, c - self.tp_pips * pip, self.name)]
        return []
