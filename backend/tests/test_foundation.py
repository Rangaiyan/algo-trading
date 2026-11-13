from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

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


def test_simulated_broker_idempotent_orders():
    b = SimulatedBroker()
    b.set_price("EURUSD", 1.0842)
    o = Order("abc-1", "EURUSD", Side.BUY, OrderType.MARKET, 0.2, stop_loss=1.0822)
    r1, r2 = b.place_order(o), b.place_order(o)
    assert r1.ok and r1.broker_order_id == r2.broker_order_id
    assert len(b.get_positions()) == 1


def test_backtest_endpoint_and_errors():
    r = client.post("/backtests", json={"strategy": "EMA-2", "days": 60, "source": "synthetic"})
    assert r.status_code == 200 and r.json()["warning"]
    assert client.post("/backtests", json={"strategy": "nope"}).status_code == 404
    assert client.post("/backtests", json={"strategy": "EMA-2", "symbol": "NOPE"}).status_code == 404


def test_backtest_returns_curve_and_trades():
    d = client.post("/backtests", json={"strategy": "EMA-2", "days": 60, "source": "synthetic"}).json()
    assert 0 < len(d["equity"]) <= 1000 and {"t", "equity", "dd"} <= d["equity"][0].keys()
    assert len(d["trades"]) == d["metrics"]["trades"]
    assert {s["id"] for s in client.get("/backtests/strategies").json()} >= {"EMA-1", "EMA-2", "EMA-3", "CANDLE-1"}


def test_status_reports_brokers_and_mode(monkeypatch):
    import app.api.routes as routes
    from app.core.config import Settings
    monkeypatch.setattr(routes, "get_settings", lambda: Settings(mt5_gateway_url="http://gw.test"))  # independent of .env / cwd
    monkeypatch.setattr(routes, "mt5_connection",lambda: {"connected": True, "detail": "Demo-Server - DEMO", "account_mode": "demo"})
    d = client.get("/status").json()
    assert d["mode"] == "demo"
    assert [b["id"] for b in d["brokers"]] == ["mt5"]  # MT5 is the only broker (OANDA is not available in India)
    assert d["brokers"][0]["connected"] is True


def test_mt5_probe_reports_unreachable_gateway(monkeypatch):
    from app.brokers import mt5_probe
    from app.core.config import Settings
    monkeypatch.setattr(mt5_probe, "get_settings", lambda: Settings(mt5_gateway_url="http://127.0.0.1:9", mt5_gateway_token="x"))
    r = mt5_probe._probe()
    assert r["connected"] is False and "not reachable" in r["detail"]


def test_mt5_probe_not_configured(monkeypatch):
    from app.brokers import mt5_probe
    from app.core.config import Settings
    monkeypatch.setattr(mt5_probe, "get_settings", lambda: Settings(mt5_gateway_url=""))
    assert mt5_probe._probe()["connected"] is False


def test_account_summary_pnl():
    from app.api.account import summarize
    now = datetime(2026, 11, 12, 15, tzinfo=UTC)
    acct = {"server": "Demo", "mode": "demo", "currency": "USD", "balance": 210.0, "equity": 212.5,
            "margin_used": 5.0, "free_margin": 207.5, "leverage": 100}
    pos = [{"id": "9", "symbol": "EURUSD", "unrealized_pnl": 2.5}]
    z = dict(commission=0.0, swap=0.0, fee=0.0, volume=0.01, price=1.1, symbol="EURUSD")
    deals = [
        {**z, "position_id": 0, "ts": "2026-11-01T00:00:00+00:00", "type": "balance", "entry": "in", "profit": 200.0},
        {**z, "position_id": 1, "ts": "2026-11-10T10:00:00+00:00", "type": "buy", "entry": "in", "profit": 0.0},
        {**z, "position_id": 1, "ts": "2026-11-10T11:00:00+00:00", "type": "sell", "entry": "out", "profit": 15.0, "commission": -0.5},
        {**z, "position_id": 2, "ts": "2026-11-12T09:00:00+00:00", "type": "sell", "entry": "in", "profit": 0.0},
        {**z, "position_id": 2, "ts": "2026-11-12T10:00:00+00:00", "type": "buy", "entry": "out", "profit": -4.5},
    ]
    d = summarize(acct, pos, deals, now)
    assert d["deposits"] == 200.0
    assert d["pnl"] == {"today": -4.5, "week": 10.0, "month": 10.0, "all": 10.0}
    assert d["total_pnl"] == 12.5 and d["floating"] == 2.5
    assert (d["trades"], d["wins"], d["losses"]) == (2, 1, 1)
    assert d["recent"][0]["position_id"] == 2 and d["recent"][0]["side"] == "sell"
    assert d["margin_level"] == 4250.0 and d["return_pct"] == 6.25


def test_desk_summary_splits_trades_by_magic():
    from app.api.account import desk_summary
    z = dict(commission=0.0, swap=0.0, fee=0.0, volume=0.01, price=1.1, symbol="EURUSD")
    def trade(pid, magic, pnl, day):
        return [{**z, "position_id": pid, "magic": magic, "ts": f"2026-11-{day:02d}T10:00:00+00:00", "type": "buy", "entry": "in", "profit": 0.0},
                {**z, "position_id": pid, "magic": magic, "ts": f"2026-11-{day:02d}T11:00:00+00:00", "type": "sell", "entry": "out", "profit": pnl}]
    deals = trade(1, 1001, 10.0, 3) + trade(2, 1002, -4.0, 4) + trade(3, 2001, 7.0, 5) + trade(4, 0, 3.0, 6)
    pos = [{"id": "9", "symbol": "GBPUSD", "magic": 1001, "unrealized_pnl": 1.5}, {"id": "8", "symbol": "EURUSD", "magic": 0, "unrealized_pnl": 2.0}]
    ema = desk_summary("ema", pos, deals)
    assert (ema["trades"], ema["net"], ema["floating"]) == (2, 6.0, 1.5)
    assert ema["profit_factor"] == 2.5 and ema["win_rate"] == 0.5
    assert [s["strategy"] for s in ema["strategies"]] == ["EMA-1", "EMA-2", "EMA-3"]
    assert ema["curve"] == [{"t": "2026-11-03T11:00:00+00:00", "cum": 10.0}, {"t": "2026-11-04T11:00:00+00:00", "cum": 6.0}]
    assert desk_summary("candle", pos, deals)["net"] == 7.0
    manual = desk_summary("manual", pos, deals)
    assert manual["trades"] == 1 and manual["positions"][0]["id"] == "8"
    assert desk_summary("ict", pos, deals)["trades"] == 0


def test_access_token_middleware():
    from fastapi.testclient import TestClient as TC

    from app.core.config import get_settings
    from app.main import create_app
    get_settings.cache_clear()
    import os
    os.environ["APP_ACCESS_TOKEN"] = "s3cret-token-for-tests-only"
    try:
        get_settings.cache_clear()
        c = TC(create_app())
        assert c.get("/health").status_code == 200                                   # open for uptime checks
        assert c.get("/markets").status_code == 401
        assert c.get("/markets", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert c.get("/markets", headers={"Authorization": "Bearer s3cret-token-for-tests-only"}).status_code == 200
        assert c.get("/markets?access_token=s3cret-token-for-tests-only").status_code == 200
        r = c.get("/markets", headers={"Origin": "http://192.168.1.20:5173"})
        assert r.status_code == 401 and r.headers.get("access-control-allow-origin") == "http://192.168.1.20:5173"
        assert "access-control-allow-origin" not in c.get("/health", headers={"Origin": "http://evil.example.com"}).headers
    finally:
        os.environ.pop("APP_ACCESS_TOKEN", None)
        get_settings.cache_clear()
