import numpy as np
import pandas as pd

from app.backtest.engine import BacktestConfig, Context, run_backtest
from app.backtest.metrics import compute_metrics
from app.data import pipeline as P
from app.data.oanda_candles import parse_candles
from app.domain import Bar, Instrument, Market
from app.strategies.candle.strategies import CandlestickBaseline
from app.strategies.ema.strategies import EMACrossover, EMATrendPullback

EURUSD = Instrument(Market.FOREX, "EURUSD")
STRATS = [EMATrendPullback, EMACrossover, CandlestickBaseline]


def collect(strategy, df):
    ctx = Context(df, EURUSD)
    strategy.on_start(ctx)
    out = []
    for i, (ts, r) in enumerate(df.iterrows()):
        ctx.i = i
        sigs = strategy.on_bar(ctx, Bar(ts.to_pydatetime(), r.open, r.high, r.low, r.close))
        out.append([(s.side, round(s.stop_loss, 8), round(s.take_profit, 8)) for s in sigs])
    return out


def test_no_lookahead_signals_unchanged_when_future_appended():
    df = P.synthetic(days=60)
    k = len(df) // 2
    for cls in STRATS:
        assert collect(cls(), df.iloc[:k]) == collect(cls(), df)[:k], cls.__name__


def test_strategies_trade_on_synthetic_and_are_deterministic():
    df = P.synthetic(days=150)
    for cls in STRATS:
        r1 = compute_metrics(run_backtest(df, cls(), EURUSD, BacktestConfig()))
        r2 = compute_metrics(run_backtest(df, cls(), EURUSD, BacktestConfig()))
        assert r1 == r2
        assert r1["trades"] > 0, f"{cls.__name__} produced no trades"


def test_cost_stress_never_improves_results():
    df = P.synthetic(days=150)
    base = BacktestConfig()
    stressed = BacktestConfig()
    stressed.costs.stress = 1.5
    a = compute_metrics(run_backtest(df, EMACrossover(), EURUSD, base))["net_profit"]
    b = compute_metrics(run_backtest(df, EMACrossover(), EURUSD, stressed))["net_profit"]
    assert b <= a


def test_resample_and_quality():
    df = P.synthetic(days=20, timeframe="M5")
    h1 = P.resample(df, "H1")
    assert h1.index.is_monotonic_increasing and len(h1) < len(df)
    assert h1["high"].iloc[0] == df["high"].iloc[:12].max()
    assert P.validate(P.clean(df), "M5").ok


def test_validate_catches_problems():
    df = P.synthetic(days=5)
    bad = pd.concat([df, df.iloc[[3]]])                  # duplicate
    bad.iloc[10, bad.columns.get_loc("high")] = bad.iloc[10]["low"] - 0.01  # high < low
    rep = P.validate(bad)
    assert rep.duplicates == 1 and rep.bad_ohlc == 1 and not rep.ok
    assert P.validate(P.clean(bad)).ok


def test_data_version_changes_with_data(tmp_path):
    df = P.synthetic(days=5)
    assert P.data_version(df) == P.data_version(df.copy())
    df2 = df.copy()
    df2.iloc[0, 0] += 0.001
    assert P.data_version(df) != P.data_version(df2)
    P.store(df, tmp_path, "EURUSD", "M15")
    assert np.allclose(P.read_store(tmp_path, "EURUSD", "M15").close, df.close)


def test_csv_import_converts_to_utc(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("time,open,high,low,close\n2026-01-15 09:00,1.1,1.2,1.0,1.15\n")
    df = P.load_csv(p, tz="America/New_York")
    assert str(df.index[0]) == "2026-01-15 14:00:00+00:00"


def test_oanda_parse_skips_incomplete_candle():
    payload = {"candles": [
        {"time": "2026-01-05T00:00:00.000000000Z", "volume": 10, "complete": True,
         "mid": {"o": "1.1", "h": "1.2", "l": "1.0", "c": "1.15"}},
        {"time": "2026-01-05T00:15:00.000000000Z", "volume": 3, "complete": False,
         "mid": {"o": "1.15", "h": "1.2", "l": "1.1", "c": "1.16"}}]}
    assert len(parse_candles(payload)) == 1
