"""Event-driven, bar-by-bar backtester (doc 10.1-10.2).

Rules enforced here:
* Signal on a CLOSED bar i executes at bar i+1 open (no look-ahead).
* Prices in data are mid; we trade bid/ask via half-spread + slippage.
* If SL and TP are both reachable inside one bar, the SL is assumed to hit (conservative).
* One position per run (single symbol); swap charged per rollover, tripled on Wednesday.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from app.backtest.costs import CostConfig, pnl_per_price_unit
from app.domain import Bar, Instrument, Side, Signal
from app.markets.forex.sessions import session_label
from app.strategies.base import Strategy


@dataclass
class Trade:
    symbol: str
    side: Side
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry_px: float
    exit_px: float
    qty: float
    pnl: float          # net of all costs
    fees: float         # commission + swap
    exit_reason: str
    strategy: str = ""
    # --- ledger detail (doc section 6.5 / reference UI needs) ---
    pips: float = 0.0
    gross_pnl: float = 0.0       # before spread, slippage, commission and swap
    commission: float = 0.0
    swap: float = 0.0
    spread_cost: float = 0.0
    slippage_cost: float = 0.0
    mfe_pips: float = 0.0        # max favourable excursion
    mae_pips: float = 0.0        # max adverse excursion
    mfe_money: float = 0.0       # peak open profit (before exit costs)
    mae_money: float = 0.0
    risk_money: float = 0.0      # money at risk at entry (SL distance x size)
    r_multiple: float = 0.0
    bars_held: int = 0
    entry_session: str = ""
    stop_loss: float = 0.0
    take_profit: float | None = None


@dataclass
class BacktestConfig:
    initial_balance: float = 10_000.0
    risk_per_trade_pct: float = 0.5
    min_lot: float = 0.01
    lot_step: float = 0.01
    max_lots: float = 50.0
    costs: CostConfig = field(default_factory=CostConfig)


@dataclass
class BacktestResult:
    trades: list[Trade]
    equity: pd.Series
    config: BacktestConfig


class Context:
    """What a strategy may see. `df` is the full frame, but only rows <= i may be read."""

    def __init__(self, df: pd.DataFrame, instrument: Instrument):
        self.df = df
        self.instrument = instrument
        self.i = 0

    def history(self, n: int | None = None) -> pd.DataFrame:
        h = self.df.iloc[: self.i + 1]
        return h if n is None else h.iloc[-n:]


@dataclass
class _Open:
    side: Side
    qty: float
    entry_px: float
    entry_ts: pd.Timestamp
    sl: float
    tp: float | None
    commission: float
    strategy: str
    swap: float = 0.0
    mfe: float = 0.0          # price units
    mae: float = 0.0
    risk_money: float = 0.0
    entry_hs: float = 0.0
    entry_slip: float = 0.0
    entry_i: int = 0


def _rollover_nights(prev_ts: pd.Timestamp, ts: pd.Timestamp) -> list[pd.Timestamp]:
    """Rollover instants (17:00 New York) crossed between two bars."""
    ny_prev, ny_now = prev_ts.tz_convert("America/New_York"), ts.tz_convert("America/New_York")
    out, d = [], ny_prev.normalize()
    while d <= ny_now.normalize():
        roll = d + pd.Timedelta(hours=17)
        if ny_prev < roll <= ny_now:
            out.append(roll)
        d += pd.Timedelta(days=1)
    return out


def run_backtest(df: pd.DataFrame, strategy: Strategy, instrument: Instrument,
                 cfg: BacktestConfig | None = None) -> BacktestResult:
    cfg = cfg or BacktestConfig()
    cs, pip = cfg.costs, instrument.pip_size
    ctx = Context(df, instrument)
    strategy.on_start(ctx)

    balance = cfg.initial_balance
    pos: _Open | None = None
    pending: Signal | None = None
    trades: list[Trade] = []
    eq: list[float] = []
    rows = df.reset_index()
    ts_col = rows.columns[0]

    def pv(qty: float, px: float) -> float:
        return pnl_per_price_unit(instrument.symbol, instrument.lot_size, qty, px)

    def close(p: _Open, ts, px: float, reason: str, exit_hs: float = 0.0, exit_slip: float = 0.0, bar_i: int = 0):
        nonlocal balance, pos
        direction = 1 if p.side == Side.BUY else -1
        unit = pv(p.qty, px)
        gross_move = (px - p.entry_px) * direction * unit
        commission = p.commission * 2
        fees = commission + p.swap
        pnl = gross_move - fees
        balance += pnl
        spread_cost = (p.entry_hs + exit_hs) * unit
        slippage_cost = (p.entry_slip + exit_slip) * unit
        trades.append(Trade(
            instrument.symbol, p.side, p.entry_ts, ts, p.entry_px, px, p.qty, pnl, fees, reason, p.strategy,
            pips=(px - p.entry_px) * direction / pip,
            gross_pnl=pnl + fees + spread_cost + slippage_cost,
            commission=commission, swap=p.swap, spread_cost=spread_cost, slippage_cost=slippage_cost,
            mfe_pips=p.mfe / pip, mae_pips=p.mae / pip,
            mfe_money=p.mfe * unit, mae_money=p.mae * unit,
            risk_money=p.risk_money, r_multiple=(pnl / p.risk_money) if p.risk_money else 0.0,
            bars_held=max(0, bar_i - p.entry_i), entry_session=session_label(p.entry_ts.to_pydatetime()),
            stop_loss=p.sl, take_profit=p.tp,
        ))
        pos = None

    prev_ts = None
    for i, r in rows.iterrows():
        ts = r[ts_col]
        bar = Bar(ts.to_pydatetime(), r.open, r.high, r.low, r.close, r.volume, r.spread)
        hs = cs.spread(bar.spread, pip) / 2
        slip = cs.slippage(pip)

        # 1) swap for any rollover crossed while a position is open
        if pos and prev_ts is not None:
            for roll in _rollover_nights(prev_ts, ts):
                mult = 3 if roll.weekday() == 2 else 1  # Wednesday = triple swap
                rate = cs.swap_long_per_lot if pos.side == Side.BUY else cs.swap_short_per_lot
                pos.swap -= rate * pos.qty * mult  # negative rate => cost => swap increases fees

        # 2) fill the pending signal at this bar's open
        if pending and pos is None:
            sig, pending = pending, None
            buy = sig.side == Side.BUY
            entry = r.open + (hs + slip) * (1 if buy else -1)
            risk_per_lot = abs(entry - sig.stop_loss) * pv(1.0, entry)
            valid_sl = (sig.stop_loss < entry) if buy else (sig.stop_loss > entry)
            if risk_per_lot > 0 and valid_sl:
                lots = (balance * cfg.risk_per_trade_pct / 100) / risk_per_lot
                lots = math.floor(lots / cfg.lot_step + 1e-9) * cfg.lot_step  # epsilon: float floor
                lots = min(lots, cfg.max_lots)
                if lots >= cfg.min_lot:
                    pos = _Open(sig.side, round(lots, 2), entry, ts, sig.stop_loss, sig.take_profit,
                                cs.commission_per_lot * round(lots, 2), sig.strategy,
                                risk_money=risk_per_lot * round(lots, 2), entry_hs=hs, entry_slip=slip, entry_i=i)

        # 3) manage the open position on this bar (SL first = conservative)
        if pos:
            if pos.side == Side.BUY:
                bid_low, bid_high = r.low - hs, r.high - hs
                pos.mfe = max(pos.mfe, bid_high - pos.entry_px)
                pos.mae = max(pos.mae, pos.entry_px - bid_low)
                if bid_low <= pos.sl:
                    close(pos, ts, min(pos.sl, r.open - hs) - slip, "sl", hs, slip, i)
                elif pos.tp is not None and bid_high >= pos.tp:
                    close(pos, ts, pos.tp, "tp", hs, 0.0, i)
            else:
                ask_low, ask_high = r.low + hs, r.high + hs
                pos.mfe = max(pos.mfe, pos.entry_px - ask_low)
                pos.mae = max(pos.mae, ask_high - pos.entry_px)
                if ask_high >= pos.sl:
                    close(pos, ts, max(pos.sl, r.open + hs) + slip, "sl", hs, slip, i)
                elif pos.tp is not None and ask_low <= pos.tp:
                    close(pos, ts, pos.tp, "tp", hs, 0.0, i)

        # 4) mark to market on close
        unreal = 0.0
        if pos:
            d = 1 if pos.side == Side.BUY else -1
            mark = r.close - hs * d
            unreal = (mark - pos.entry_px) * d * pv(pos.qty, mark) - pos.commission * 2 - pos.swap
        eq.append(balance + unreal)

        # 5) strategy sees the CLOSED bar; its signal executes next bar
        ctx.i = i
        sigs = strategy.on_bar(ctx, bar)
        if sigs and pos is None and pending is None:
            pending = sigs[0]
        prev_ts = ts

    if pos:  # close any open trade at the final close
        last = rows.iloc[-1]
        hs = cs.spread(last.spread, pip) / 2
        px = last.close - hs if pos.side == Side.BUY else last.close + hs
        close(pos, last[ts_col], px, "end", hs, 0.0, len(rows) - 1)
        eq[-1] = balance
    strategy.on_stop(ctx)
    return BacktestResult(trades, pd.Series(eq, index=df.index, name="equity"), cfg)
