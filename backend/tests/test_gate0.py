"""Gate 0: the comparison logic itself (self-consistency) and the bid price basis."""
import numpy as np
import pandas as pd
import pytest

from app.backtest import runner
from app.backtest.engine import BacktestConfig, run_backtest
from app.data import pipeline as P
from app.domain import Bar, Instrument, Market, Side, Signal
from app.gates import gate0
from app.strategies.base import Strategy
from app.strategies.reference import Gate0Reference

EURUSD = Instrument(Market.FOREX, "EURUSD")


def _ea_csv_from(trades, lots=0.1) -> str:
    rows = ["position_id,side,open_time,open_price,close_time,close_price,volume,profit,commission,swap,reason,symbol,timeframe,fast,slow,sl_pips,tp_pips"]
    for k, t in enumerate(trades):
        reason = 4 if t.exit_reason == "sl" else 5 if t.exit_reason == "tp" else 0
        rows.append(f"{k},{t.side.value},{int(t.entry_ts.timestamp()) + 3},{t.entry_px:.5f},{int(t.exit_ts.timestamp()) + 7},"
                    f"{t.exit_px:.5f},{lots},{t.pnl + t.fees:.2f},0,{-t.swap:.2f},{reason},EURUSD,PERIOD_M15,20,50,30,60")
    return "\n".join(rows)


@pytest.fixture
def store(tmp_path, monkeypatch):
    df = P.synthetic(days=120)
    P.store(df, tmp_path, "EURUSD", "M15")
    (tmp_path / "EURUSD" / "M15.meta.json").write_text('{"source": "mt5", "holdout_start": "2030-01-01", "spec": null}')
    monkeypatch.setattr(runner, "DATA_ROOT", str(tmp_path))
    return df


def _reference_trades(df):
    start = df.index[1500]
    cfg = BacktestConfig(fixed_lots=0.1)
    cfg.costs.price_basis, cfg.costs.slippage_pips = "bid", 0.0
    res = run_backtest(df.iloc[1500 - gate0.WARMUP_BARS:], Gate0Reference(trade_from=str(start)), EURUSD, cfg)
    return [t for t in res.trades if t.entry_ts >= start]


def test_identical_trades_pass_gate0(store):
    trades = _reference_trades(store)
    assert len(trades) > 10
    r = gate0.compare(_ea_csv_from(trades))
    assert r["verdict"] == "pass", r["checks"]
    assert r["summary"]["match_rate"] == 1.0 and r["summary"]["median_entry_diff_pips"] < 0.1  # 5-decimal rounding only


def test_shifted_entries_fail_gate0(store):
    trades = _reference_trades(store)
    text = _ea_csv_from(trades)
    lines = text.splitlines()
    bad = [lines[0]] + [",".join(f if i != 3 else f"{float(f) + 0.0015:.5f}" for i, f in enumerate(ln.split(","))) for ln in lines[1:]]
    r = gate0.compare("\n".join(bad))
    assert r["verdict"] == "fail"
    assert not next(c for c in r["checks"] if c["check"].startswith("Entry price"))["ok"]


class _BuyOnce(Strategy):
    def on_bar(self, ctx, bar):
        return [Signal("EURUSD", Side.BUY, None, bar.close - 0.01, bar.close + 0.01, "T")] if ctx.i == 0 else []


def test_bid_basis_buys_at_ask_and_exits_on_bid():
    idx = pd.date_range("2026-01-05", periods=3, freq="15min", tz="UTC")
    df = pd.DataFrame({"open": [1.1, 1.1, 1.1], "high": [1.1, 1.1, 1.1], "low": [1.1, 1.1, 1.1], "close": [1.1, 1.1, 1.1],
                       "volume": 1.0, "spread": 0.0002}, index=idx)
    for basis, entry in (("bid", 1.1002), ("mid", 1.1001)):
        cfg = BacktestConfig(fixed_lots=1.0)
        cfg.costs.price_basis, cfg.costs.slippage_pips = basis, 0.0
        t = run_backtest(df, _BuyOnce(), EURUSD, cfg).trades[0]
        assert t.entry_px == pytest.approx(entry)
        assert t.exit_px == pytest.approx(1.1 if basis == "bid" else 1.0999)   # closed at the end on the bid
        assert np.isclose(t.spread_cost, 20.0)                                  # one full spread either way ($20 / lot)
