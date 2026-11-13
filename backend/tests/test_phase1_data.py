"""Phase 1 completion: real-history ingestion, hold-out, broker swap costs, patterns, MT5 data adapter."""
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from app.backtest import runner
from app.backtest.costs import swap_from_spec
from app.brokers.mt5 import MT5Broker
from app.data import mt5_history as H
from app.data import pipeline as P
from app.domain import Side
from app.patterns import candles as C

SPEC = {"name": "EURUSD", "point": 0.00001, "contract_size": 100000.0, "currency_profit": "USD",
        "swap_mode": 1, "swap_long": -7.5, "swap_short": 2.0, "swap_rollover3days": 3}


class FakeGateway:
    """Serves M15 bars for a fixed window, like the real gateway (range-filtered)."""

    def __init__(self, first: datetime, last: datetime):
        idx = pd.date_range(first, last, freq="15min", tz="UTC")
        self.bars = [b for b in idx if b.day_of_week < 5]
        self.calls = []

    def symbol(self, symbol):
        return dict(SPEC, name=symbol)

    def status(self):
        return {"server": "Fake-Demo", "account_mode": "demo", "max_bars": 100000}

    def candles(self, symbol, timeframe, start, end):
        self.calls.append((start, end))
        return [{"ts": b.isoformat(), "open": 1.1, "high": 1.101, "low": 1.099, "close": 1.1005,
                 "volume": 10, "spread": 8} for b in self.bars if start <= b <= end]

    def get(self, path, **params):
        if path == "/account":
            return {"currency": "USD", "balance": 200.0, "equity": 201.5, "margin_used": 3.0}
        if path == "/positions":
            return [{"id": "7", "symbol": "EURUSD", "side": "buy", "qty": 0.01, "entry_price": 1.1,
                     "stop_loss": 1.09, "take_profit": None, "unrealized_pnl": 1.5}]
        raise KeyError(path)


def test_to_frame_converts_spread_points_to_price():
    df = H.to_frame([{"ts": "2026-01-05T10:00:00+00:00", "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15,
                      "volume": 5, "spread": 12}], point=0.00001)
    assert str(df.index.tz) == "UTC" and df.spread.iat[0] == pytest.approx(0.00012)


def test_download_chunks_stores_meta_and_tops_up(tmp_path):
    now = datetime(2026, 11, 13, 12, tzinfo=UTC)
    gw = FakeGateway(now - timedelta(days=400), now)
    meta = H.download(gw, tmp_path, "EURUSD", "M15", years=1, now=now, log=lambda _: None)
    assert len(gw.calls) > 1  # 1 year of M15 does not fit in one chunk
    df = P.read_store(tmp_path, "EURUSD", "M15")
    assert meta["bars"] == len(df) and meta["quality"]["ok"] and meta["data_version"] == P.data_version(df)
    assert df.index[-1] < pd.Timestamp(now) - pd.Timedelta(minutes=15)  # still-forming bar dropped
    assert pd.Timestamp(meta["holdout_start"]) == df.index[-1] - pd.DateOffset(months=6)
    assert meta["spec"]["swap_long"] == -7.5

    # a second run only fetches from the last stored day onwards
    later = now + timedelta(days=2)
    gw2 = FakeGateway(now - timedelta(days=400), later)
    meta2 = H.download(gw2, tmp_path, "EURUSD", "M15", years=1, now=later, log=lambda _: None)
    assert min(s for s, _ in gw2.calls) >= now - timedelta(days=2)
    assert meta2["bars"] > meta["bars"] and meta2["start"] == meta["start"]
    assert [m["timeframe"] for m in H.catalog(tmp_path)] == ["M15"]


def test_runner_uses_store_and_excludes_holdout(tmp_path, monkeypatch):
    now = datetime(2026, 11, 13, 12, tzinfo=UTC)
    gw = FakeGateway(now - timedelta(days=300), now)
    meta = H.download(gw, tmp_path, "EURUSD", "M15", years=1, now=now, log=lambda _: None)
    # swap the flat fake prices for tradeable ones; the meta (hold-out, spec) stays
    P.store(P.synthetic(start=(now - timedelta(days=300)).strftime("%Y-%m-%d"), days=300), tmp_path, "EURUSD", "M15")
    monkeypatch.setattr(runner, "DATA_ROOT", str(tmp_path))

    r = runner.run("EMA-2")
    assert r["source"] == "store" and r["warning"] is None
    assert pd.Timestamp(r["range"][1]) < pd.Timestamp(meta["holdout_start"])
    assert r["costs"]["swap_from_broker"] and r["costs"]["swap_long_per_lot"] == pytest.approx(-7.5)

    full = runner.run("EMA-2", include_holdout=True)
    assert full["bars"] > r["bars"] and full["includes_holdout"] and full["warning"]
    assert runner.run("EMA-2", days=30)["bars"] < r["bars"]
    with pytest.raises(FileNotFoundError):
        runner.run("EMA-2", timeframe="H4")


def test_spread_floor_never_below_typical_spread():
    from app.backtest.costs import CostConfig
    c = CostConfig(min_spread=0.00009)
    assert c.spread(0.00001, 0.0001) == pytest.approx(0.00009)  # recorded bar minimum is too optimistic
    assert c.spread(0.0003, 0.0001) == pytest.approx(0.0003)    # wider recorded spread is kept
    assert CostConfig().spread(0.00001, 0.0001) == pytest.approx(0.00001)  # no floor by default


def test_swap_from_spec_converts_points_to_usd():
    s = swap_from_spec(SPEC, 1.1)
    assert s == {"swap_long_per_lot": -7.5, "swap_short_per_lot": 2.0, "triple_swap_weekday": 2}  # MT5 Wed=3 -> Python 2
    jpy = swap_from_spec({**SPEC, "point": 0.001, "currency_profit": "JPY", "swap_long": 15.0}, 150.0)
    assert jpy["swap_long_per_lot"] == pytest.approx(15 * 0.001 * 100000 / 150, abs=1e-4)
    assert swap_from_spec({**SPEC, "swap_mode": 2}, 1.1) is None


def _frame(rows):
    pad = [(1.1000, 1.1010, 1.0990, 1.1002)] * 20  # warm-up so ATR exists
    idx = pd.date_range("2026-01-05", periods=len(pad) + len(rows), freq="15min", tz="UTC")
    return pd.DataFrame(pad + rows, columns=["open", "high", "low", "close"], index=idx)


def test_new_candle_patterns_fire_on_textbook_shapes():
    star = _frame([(1.1000, 1.1002, 1.0960, 1.0965), (1.0964, 1.0966, 1.0958, 1.0962), (1.0963, 1.0995, 1.0961, 1.0992)])
    assert C.morning_star(star).iat[-1] and not C.evening_star(star).iat[-1]
    soldiers = _frame([(1.1000, 1.1022, 1.0999, 1.1020), (1.1020, 1.1042, 1.1019, 1.1040), (1.1040, 1.1062, 1.1039, 1.1060)])
    assert C.three_white_soldiers(soldiers).iat[-1] and not C.three_black_crows(soldiers).iat[-1]
    tweez = _frame([(1.1010, 1.1012, 1.0980, 1.0985), (1.0985, 1.1008, 1.0980, 1.1005)])
    assert C.tweezer_bottom(tweez).iat[-1]
    ib = _frame([(1.1000, 1.1040, 1.0960, 1.1010), (1.1010, 1.1030, 1.0980, 1.1000), (1.1000, 1.1050, 1.0995, 1.1045)])
    assert C.inside_bar_breakout(ib)[0].iat[-1]
    assert C.doji(_frame([(1.1000, 1.1015, 1.0985, 1.1001)])).iat[-1]


def test_mt5_broker_data_methods_and_phase5_guard():
    b = MT5Broker(gateway=FakeGateway(datetime(2026, 1, 5, tzinfo=UTC), datetime(2026, 1, 6, tzinfo=UTC)))
    assert b.get_account().equity == 201.5
    p = b.get_positions()[0]
    assert p.side == Side.BUY and p.take_profit is None
    df = b.get_candles("EURUSD", "M15", datetime(2026, 1, 5, tzinfo=UTC), datetime(2026, 1, 5, 2, tzinfo=UTC))
    assert len(df) == 9 and df.spread.iat[0] == pytest.approx(0.00008)
    with pytest.raises(NotImplementedError):
        b.place_order(None)
