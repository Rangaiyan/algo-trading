from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.brokers.oanda import lots_to_units
from app.brokers.simulated import SimulatedBroker
from app.domain import Order, OrderType, Side
from app.main import app
from app.markets.forex.sessions import forex_market_open, in_session, to_ny

client = TestClient(app)


def test_health_and_markets():
    assert client.get("/health").json() == {"status": "ok"}
    markets = {m["market"]: m for m in client.get("/markets").json()}
    assert markets["forex"]["enabled"] is True
    assert markets["india"]["enabled"] is False


def test_live_trading_disabled_by_default():
    assert client.get("/status").json()["live_trading_enabled"] is False


def test_india_instruments_blocked():
    assert client.get("/instruments", params={"market": "india"}).status_code == 409
    assert len(client.get("/instruments", params={"market": "forex"}).json()) == 5


def test_kill_zone_respects_dst():
    # 07:00 UTC in January = 02:00 NY (EST) -> inside London kill zone
    assert in_session(datetime(2026, 1, 15, 7, 0, tzinfo=UTC), "london_kz")
    # 07:00 UTC in July = 03:00 NY (EDT) -> also inside; 06:00 UTC July = 02:00 NY
    assert in_session(datetime(2026, 7, 15, 6, 0, tzinfo=UTC), "london_kz")
    # 06:00 UTC in January = 01:00 NY -> outside
    assert not in_session(datetime(2026, 1, 15, 6, 0, tzinfo=UTC), "london_kz")


def test_asia_session_crosses_midnight():
    # 03:00 UTC in January = 22:00 NY previous day -> inside Asia
    assert in_session(datetime(2026, 1, 15, 3, 0, tzinfo=UTC), "asia")
    assert to_ny(datetime(2026, 1, 15, 3, 0, tzinfo=UTC)).hour == 22


def test_naive_timestamp_rejected():
    with pytest.raises(ValueError):
        to_ny(datetime(2026, 1, 15, 3, 0))


def test_forex_weekend_closed():
    assert not forex_market_open(datetime(2026, 11, 14, 12, 0, tzinfo=UTC))  # Saturday
    assert forex_market_open(datetime(2026, 11, 11, 12, 0, tzinfo=UTC))  # Wednesday


def test_oanda_units():
    assert lots_to_units(0.2, True) == 20_000
    assert lots_to_units(0.2, False) == -20_000


def test_simulated_broker_idempotent_orders():
    b = SimulatedBroker()
    b.set_price("EURUSD", 1.0842)
    o = Order("abc-1", "EURUSD", Side.BUY, OrderType.MARKET, 0.2, stop_loss=1.0822)
    r1, r2 = b.place_order(o), b.place_order(o)
    assert r1.ok and r1.broker_order_id == r2.broker_order_id
    assert len(b.get_positions()) == 1


def test_backtest_endpoint_and_errors():
    r = client.post("/backtests", json={"strategy": "EMA-2", "days": 60})
    assert r.status_code == 200 and r.json()["warning"]
    assert client.post("/backtests", json={"strategy": "nope"}).status_code == 404
    assert client.post("/backtests", json={"strategy": "EMA-2", "source": "store"}).status_code == 404


def test_backtest_returns_curve_and_trades():
    d = client.post("/backtests", json={"strategy": "EMA-2", "days": 60}).json()
    assert 0 < len(d["equity"]) <= 1000 and {"t", "equity", "dd"} <= d["equity"][0].keys()
    assert len(d["trades"]) == d["metrics"]["trades"]
    assert {s["id"] for s in client.get("/backtests/strategies").json()} >= {"EMA-1", "EMA-2"}


def test_status_reports_brokers_and_mode():
    d = client.get("/status").json()
    assert d["mode"] == "demo"
    assert {b["id"] for b in d["brokers"]} == {"mt5", "oanda"}
    assert all(b["connected"] is False for b in d["brokers"])  # nothing is connected yet
