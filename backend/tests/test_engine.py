"""Hand-calculated engine scenarios (doc 22). Costs are zeroed so the arithmetic is checkable."""
import pandas as pd
import pytest

from app.backtest.costs import CostConfig
from app.backtest.engine import BacktestConfig, Context, run_backtest
from app.backtest.metrics import compute_metrics
from app.domain import Instrument, Market, Side, Signal
from app.strategies.base import Strategy

EURUSD = Instrument(Market.FOREX, "EURUSD", pip_size=0.0001, lot_size=100_000)
ZERO = CostConfig(spread_pips=0, slippage_pips=0, commission_per_lot=0, swap_long_per_lot=0,
                  swap_short_per_lot=0)


class OneShot(Strategy):
    """Emits one signal on bar 0."""

    def __init__(self, side, sl, tp):
        super().__init__()
        self.sig = Signal("EURUSD", side, None, sl, tp, "test")

    def on_bar(self, ctx, bar):
        return [self.sig] if ctx.i == 0 else []


def frame(rows, start="2026-11-09 08:00", freq="15min"):
    idx = pd.date_range(start, periods=len(rows), freq=freq, tz="UTC")
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)
    df["volume"], df["spread"] = 0.0, 0.0
    return df


def cfg(costs=ZERO):
    return BacktestConfig(initial_balance=10_000, risk_per_trade_pct=1.0, costs=costs)


def test_take_profit_hand_calc():
    df = frame([(1.1000, 1.1005, 1.0998, 1.1000),   # bar0: signal
                (1.1000, 1.1010, 1.0995, 1.1008),   # bar1: fill @ open 1.1000
                (1.1008, 1.1025, 1.1005, 1.1020)])  # bar2: TP 1.1020 touched
    res = run_backtest(df, OneShot(Side.BUY, 1.0990, 1.1020), EURUSD, cfg())
    (t,) = res.trades
    assert t.entry_px == 1.1000 and t.exit_reason == "tp"
    assert t.qty == 1.0                      # 1% of 10k = $100 risk / (0.0010 * 100k) = 1 lot
    assert t.pnl == pytest.approx(200.0)     # 0.0020 * 100,000


def test_signal_fills_next_bar_not_same_bar():
    df = frame([(1.1000, 1.1000, 1.1000, 1.1000), (1.1050, 1.1050, 1.1050, 1.1050),
                (1.1050, 1.1050, 1.1050, 1.1050)])
    res = run_backtest(df, OneShot(Side.BUY, 1.1000, None), EURUSD, cfg())
    assert res.trades[0].entry_px == 1.1050   # bar1 open, never bar0 close


def test_same_bar_sl_and_tp_assumes_stop_first():
    df = frame([(1.1000, 1.1000, 1.1000, 1.1000),
                (1.1000, 1.1030, 1.0985, 1.1000)])  # touches both SL 1.0990 and TP 1.1020
    res = run_backtest(df, OneShot(Side.BUY, 1.0990, 1.1020), EURUSD, cfg())
    assert res.trades[0].exit_reason == "sl"
    assert res.trades[0].pnl == pytest.approx(-100.0)


def test_short_stop_loss():
    df = frame([(1.1000, 1.1000, 1.1000, 1.1000), (1.1000, 1.1012, 1.0995, 1.1005)])
    res = run_backtest(df, OneShot(Side.SELL, 1.1010, 1.0980), EURUSD, cfg())
    assert res.trades[0].exit_reason == "sl" and res.trades[0].pnl == pytest.approx(-100.0)


def test_spread_and_commission_reduce_pnl():
    df = frame([(1.1000, 1.1000, 1.1000, 1.1000), (1.1000, 1.1010, 1.0995, 1.1008),
                (1.1008, 1.1025, 1.1005, 1.1020)])
    costs = CostConfig(spread_pips=2, slippage_pips=0, commission_per_lot=3.5, swap_long_per_lot=0)
    gross = run_backtest(df, OneShot(Side.BUY, 1.0990, 1.1020), EURUSD, cfg()).trades[0].pnl
    net = run_backtest(df, OneShot(Side.BUY, 1.0990, 1.1020), EURUSD, cfg(costs)).trades[0]
    assert net.fees == pytest.approx(7.0 * net.qty)       # 3.5 each side
    assert net.pnl < gross


def test_wednesday_triple_swap():
    # Wed 2026-11-11, rollover = 17:00 NY = 22:00 UTC (EST). Bars hourly, flat price.
    df = frame([(1.1, 1.1, 1.1, 1.1)] * 4, start="2026-11-11 20:00", freq="1h")
    costs = CostConfig(spread_pips=0, slippage_pips=0, swap_long_per_lot=-3.0)
    res = run_backtest(df, OneShot(Side.BUY, 1.099, None), EURUSD, cfg(costs))
    t = res.trades[0]
    assert t.exit_reason == "end" and t.fees == pytest.approx(3.0 * 3 * t.qty)


def test_metrics_basic():
    df = frame([(1.1000, 1.1000, 1.1000, 1.1000), (1.1000, 1.1010, 1.0995, 1.1008),
                (1.1008, 1.1025, 1.1005, 1.1020)])
    m = compute_metrics(run_backtest(df, OneShot(Side.BUY, 1.0990, 1.1020), EURUSD, cfg()))
    assert m["trades"] == 1 and m["net_profit"] == 200.0 and m["win_rate"] == 1.0


def test_naive_index_rejected_by_pipeline():
    from app.data.pipeline import normalize
    with pytest.raises(ValueError):
        normalize(pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]},
                               index=pd.DatetimeIndex(["2026-01-01"])))


def test_context_history_never_exceeds_current_bar():
    df = frame([(1, 1, 1, 1)] * 5)
    ctx = Context(df, EURUSD)
    ctx.i = 2
    assert len(ctx.history()) == 3


def test_trade_ledger_fields_hand_calc():
    df = frame([(1.1000, 1.1005, 1.0998, 1.1000),
                (1.1000, 1.1010, 1.0995, 1.1008),
                (1.1008, 1.1025, 1.1005, 1.1020)])
    t = run_backtest(df, OneShot(Side.BUY, 1.0990, 1.1020), EURUSD, cfg()).trades[0]
    assert t.pips == pytest.approx(20.0)
    assert t.mfe_pips == pytest.approx(25.0)      # best bid reached 1.1025
    assert t.mae_pips == pytest.approx(5.0)       # worst bid 1.0995
    assert t.risk_money == pytest.approx(100.0)
    assert t.r_multiple == pytest.approx(2.0)
    assert t.gross_pnl == pytest.approx(200.0) and t.spread_cost == 0 and t.commission == 0
    assert t.bars_held == 1
    assert t.mfe_money == pytest.approx(250.0)


def test_cost_breakdown_reconciles_to_gross():
    df = frame([(1.1000, 1.1000, 1.1000, 1.1000), (1.1000, 1.1010, 1.0995, 1.1008),
                (1.1008, 1.1025, 1.1005, 1.1020)])
    costs = CostConfig(spread_pips=2, slippage_pips=0, commission_per_lot=3.5, swap_long_per_lot=0)
    t = run_backtest(df, OneShot(Side.BUY, 1.0990, 1.1020), EURUSD, cfg(costs)).trades[0]
    assert t.commission == pytest.approx(7.0 * t.qty)
    assert t.spread_cost == pytest.approx(20.0 * t.qty)           # 2 pips x $10/pip/lot x qty
    # net = gross - spread - slippage - commission - swap
    assert t.pnl == pytest.approx(t.gross_pnl - t.spread_cost - t.slippage_cost - t.commission - t.swap)


def test_entry_session_label_follows_dst():
    from datetime import UTC, datetime

    from app.markets.forex.sessions import session_label
    assert session_label(datetime(2026, 1, 15, 14, 0, tzinfo=UTC)) == "london+newyork"   # 09:00 NY, 14:00 London
    assert session_label(datetime(2026, 7, 15, 12, 30, tzinfo=UTC)) == "london+newyork"
    assert session_label(datetime(2026, 7, 15, 17, 0, tzinfo=UTC)) == "newyork"          # London closed (18:00 BST)
    assert session_label(datetime(2026, 11, 14, 12, 0, tzinfo=UTC)) == "off-hours"       # Saturday
