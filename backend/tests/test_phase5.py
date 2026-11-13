"""Phase 5: trading engine against a fake MT5 gateway, risk manager, kill switch, investment maths, reports, commands."""
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from app.backtest import runner
from app.brokers.mt5 import MT5Broker
from app.domain import Side, Signal
from app.execution.commands import CommandHandler
from app.execution.engine import TradingEngine, tag_for
from app.portfolio import investment as INV
from app.reports import reports as R
from app.risk.manager import RiskManager, lot_loss_usd, usd_direction
from app.strategies.base import Strategy

SPEC = {"name": "EURUSD", "point": 0.00001, "contract_size": 100000.0, "volume_min": 0.01, "volume_step": 0.01,
        "volume_max": 50.0, "spread_points": 8, "currency_profit": "USD"}
ACC = {"currency": "USD", "balance": 10000.0, "equity": 10000.0, "margin_used": 0.0, "free_margin": 10000.0}


class AlwaysBuy(Strategy):
    """Test strategy: market buy on every closed bar, 20-pip stop, 40-pip target."""
    name = "TEST-BUY"

    def on_bar(self, ctx, bar):
        return [Signal(ctx.instrument.symbol, Side.BUY, None, bar.close - 0.0020, bar.close + 0.0040, self.name)]


class FakeGW:
    def __init__(self, clock):
        self.clock = clock
        self.positions, self.pending, self.deals, self.sent = [], [], [], []
        self.account = dict(ACC)
        self.connected = True
        self._ticket = 1000

    def status(self):
        return {"terminal_connected": self.connected}

    def symbol(self, s):
        return dict(SPEC, name=s)

    def candles(self, symbol, tf, start, end):
        idx = pd.date_range(end=pd.Timestamp(self.clock()).floor("15min"), periods=900, freq="15min")
        return [{"ts": t.isoformat(), "open": 1.1, "high": 1.1006, "low": 1.0994, "close": 1.1002, "volume": 1, "spread": 8} for t in idx]

    def get(self, path, **kw):
        return {"/account": self.account, "/positions": self.positions, "/orders": self.pending,
                "/deals": self.deals, "/ticks": {"EURUSD": {"bid": 1.1002, "ask": 1.10028}}}[path]

    def send(self, method, path, body=None):
        self.sent.append((method, path, body))
        self._ticket += 1
        if path == "/orders" and method == "POST":
            tag = tag_for(body["client_id"])
            if any(p["tag"] == tag for p in self.positions):
                return {"ok": True, "duplicate": True}
            if body["type"] == "market":
                self.positions.append({"id": str(self._ticket), "symbol": body["symbol"], "side": body["side"], "qty": body["volume"],
                                       "entry_price": 1.10031, "stop_loss": body["stop_loss"], "take_profit": body["take_profit"],
                                       "unrealized_pnl": 0.0, "magic": body["magic"], "tag": tag, "opened_at": self.clock().isoformat()})
            else:
                self.pending.append({"ticket": self._ticket, "symbol": body["symbol"], "magic": body["magic"], "tag": tag})
            return {"ok": True, "retcode": 10009, "order": self._ticket, "price": 1.10031, "latency_ms": 42.0}
        if path.endswith("/close"):
            tid = path.split("/")[2]
            self.positions = [p for p in self.positions if p["id"] != tid]
            return {"ok": True}
        if method == "DELETE":
            tid = int(path.split("/")[2])
            self.pending = [o for o in self.pending if o["ticket"] != tid]
            return {"ok": True}
        raise KeyError(path)

    def close_at(self, tag, price, pnl):
        p = next(x for x in self.positions if x["tag"] == tag)
        self.positions.remove(p)
        base = {"commission": 0.0, "swap": 0.0, "fee": 0.0, "position_id": int(p["id"]), "symbol": p["symbol"], "volume": p["qty"],
                "magic": p["magic"], "type": "buy"}
        self.deals += [{**base, "entry": "in", "price": p["entry_price"], "profit": 0.0, "ts": p["opened_at"], "comment": tag},
                       {**base, "entry": "out", "type": "sell", "price": price, "profit": pnl, "ts": self.clock().isoformat(), "comment": ""}]


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setitem(runner.STRATEGIES, "TEST-BUY", AlwaysBuy)
    t = {"now": datetime(2026, 11, 10, 10, 7, tzinfo=UTC)}  # a Tuesday
    clock = lambda: t["now"]  # noqa: E731
    gw = FakeGW(clock)
    from app.risk.news import NewsCalendar
    eng = TradingEngine(MT5Broker(gateway=gw), root=str(tmp_path), now=clock,
                        news=NewsCalendar(str(tmp_path), fetch=lambda: []))  # no network in tests
    return eng, gw, t


def test_full_trade_lifecycle_and_no_duplicates(rig):
    eng, gw, t = rig
    s = eng.add_session("TEST-BUY", "EURUSD", "M15", name="test")
    eng.set_status(s["id"], "running")
    assert eng.tick() == [] and gw.sent == []                     # first pass only remembers the latest candle
    t["now"] += timedelta(minutes=15)
    eng.tick()                                                    # new closed candle -> signal -> order
    assert len(gw.sent) == 1 and gw.sent[0][2]["magic"] == s["magic"] and gw.sent[0][2]["stop_loss"] < 1.10028
    rec = eng.orders[-1]
    assert rec["state"] == "pending" and rec["lots"] == 0.24  # $50 risk / $208 per lot (stop 20.8 pips from the ask)
    alerts = eng.tick()                                           # reconcile: position is there -> open
    assert rec["state"] == "open" and rec["slippage_pips"] == pytest.approx((1.10031 - 1.10028) / 0.0001, abs=0.01)
    assert any("TRADE OPENED" in a for a, _ in alerts)
    t["now"] += timedelta(minutes=15)
    eng.tick()                                                    # same session already in a trade -> no new order
    assert len(gw.sent) == 1 and "already has an open trade" in s["last_signal"]["decision"]
    gw.close_at(rec["tag"], 1.1043, 100.0)
    alerts = eng.tick()
    assert rec["state"] == "closed" and rec["pnl"] == 100.0 and rec["exit_reason"] == "tp"
    assert any("TRADE CLOSED" in a for a, _ in alerts)
    # restart: a new engine reading the same files must not resend for an already-handled candle
    eng2 = TradingEngine(eng.broker, root=str(eng.root), now=eng.now, news=eng.news)
    s2 = eng2.session(s["id"])
    s2["last_bar"] = rec["signal_bar"]
    eng2.orders[-1]["state"] = "open"  # pretend still open so the signal is skipped by the one-trade rule
    gw.positions.append({"id": "9", "symbol": "EURUSD", "side": "buy", "qty": 0.25, "entry_price": 1.1, "tag": rec["tag"], "magic": s["magic"]})
    eng2.tick()
    assert len(gw.sent) == 1


def test_risk_rejection_and_daily_halt(rig):
    eng, gw, t = rig
    s = eng.add_session("TEST-BUY", "EURUSD", "M15")
    eng.set_status(s["id"], "running")
    eng.tick()
    gw.account = dict(ACC, equity=9790.0)      # -2.1% today
    t["now"] += timedelta(minutes=15)
    alerts = eng.tick()
    assert eng.risk.halted and eng.risk.state["halt"] == "daily"
    assert any("DAILY LOSS LIMIT" in a for a, _ in alerts) and gw.sent == []
    t["now"] += timedelta(days=1)              # next trading day: daily halt clears by itself
    eng.tick()
    assert not eng.risk.halted


def test_kill_switch_flattens_only_rinz_positions(rig):
    eng, gw, _ = rig
    gw.positions = [{"id": "1", "symbol": "EURUSD", "side": "buy", "magic": 1002, "tag": "rz:abc"},
                    {"id": "2", "symbol": "GBPUSD", "side": "sell", "magic": 0, "tag": ""}]
    gw.pending = [{"ticket": 7, "symbol": "EURUSD", "magic": 4001, "tag": "rz:def"}]
    s = eng.add_session("TEST-BUY", "EURUSD", "M15")
    eng.set_status(s["id"], "running")
    r = eng.kill()
    assert [x["ticket"] for x in r["closed"]] == ["1"] and [x["ticket"] for x in r["cancelled"]] == [7]
    assert [p["id"] for p in gw.positions] == ["2"]          # the manual trade is untouched
    assert eng.risk.state["halt"] == "kill" and s["status"] == "paused"
    with pytest.raises(ValueError):
        eng.set_status(s["id"], "running")                   # cannot restart while kill-halted
    eng.risk.resume()
    assert eng.set_status(s["id"], "running")["status"] == "running"


def test_reconcile_flags_unknown_rinz_position_and_expires_limits(rig):
    eng, gw, _ = rig
    gw.positions = [{"id": "55", "symbol": "EURUSD", "side": "buy", "magic": 1001, "tag": "rz:unknown"}]
    eng.orders.append({"tag": "rz:gone", "client_id": "x", "session_id": "s", "session_name": "s", "strategy": "EMA-1",
                       "symbol": "EURUSD", "side": "buy", "state": "pending", "placed_at": "2026-11-10T09:00:00+00:00",
                       "requested_price": 1.1, "lots": 0.1, "mode": "paper", "stop_loss": 1.09, "take_profit": 1.12, "risk_money": 10})
    alerts = eng.tick()
    assert eng.orders[-1]["state"] == "expired"
    assert any("no record" in a for a, _ in alerts) and eng.state["issues"]


def test_disconnect_alert_once_then_reconnect(rig):
    eng, gw, _ = rig
    gw.connected = False
    assert any("DISCONNECTED" in a for a, _ in eng.tick())
    assert eng.tick() == []
    gw.connected = True
    assert any("RECONNECTED" in a for a, _ in eng.tick())


def test_risk_sizing_and_limits(tmp_path):
    rm = RiskManager(str(tmp_path))
    acc = dict(ACC)
    d = rm.check(symbol="EURUSD", side="buy", entry=1.1, stop=1.098, account=acc, positions=[], spec=SPEC, pip_size=0.0001, trades_today=0)
    assert d.ok and d.lots == 0.25 and d.risk_money == 50.0
    assert lot_loss_usd("USDJPY", 150.0, 149.5, 100000) == pytest.approx(0.5 * 100000 / 150)
    assert usd_direction("EURUSD", "buy") == -1 and usd_direction("USDJPY", "buy") == 1 and usd_direction("EURGBP", "buy") == 0
    two_short_usd = [{"symbol": "EURUSD", "side": "buy"}, {"symbol": "GBPUSD", "side": "buy"}]
    assert "USD exposure" in rm.check(symbol="AUDUSD", side="buy", entry=0.66, stop=0.658, account=acc, positions=two_short_usd,
                                       spec=SPEC, pip_size=0.0001, trades_today=0).reason
    wide = rm.check(symbol="EURUSD", side="buy", entry=1.1, stop=1.0, account=dict(ACC, equity=100.0), positions=[], spec=SPEC,
                    pip_size=0.0001, trades_today=0)
    assert not wide.ok and "too wide" in wide.reason
    assert "spread" in rm.check(symbol="EURUSD", side="buy", entry=1.1, stop=1.098, account=acc, positions=[],
                                spec=dict(SPEC, spread_points=40), pip_size=0.0001, trades_today=0).reason
    with pytest.raises(ValueError):
        rm.update_config({"max_risk_pct": 5})
    rm.observe_equity(10000.0, datetime(2026, 11, 10, 12, tzinfo=UTC))
    rm.observe_equity(8900.0, datetime(2026, 11, 10, 13, tzinfo=UTC))   # -11% from peak
    assert rm.state["halt"] == "drawdown"
    rm.observe_equity(8900.0, datetime(2026, 11, 12, 13, tzinfo=UTC))
    assert rm.state["halt"] == "drawdown"                                  # needs a manual resume


def test_investment_twr_xirr_and_reports():
    now = datetime(2026, 3, 1, tzinfo=UTC)
    z = {"commission": 0.0, "swap": 0.0, "fee": 0.0, "magic": 1001}
    deals = [{**z, "ts": "2025-03-01T00:00:00+00:00", "type": "balance", "profit": 1000.0},
             {**z, "ts": "2025-09-01T00:00:00+00:00", "type": "sell", "profit": 100.0},
             {**z, "ts": "2025-09-02T00:00:00+00:00", "type": "balance", "profit": 1000.0}]
    s = INV.summary(deals, {"equity": 2100.0, "currency": "USD"}, [], now)
    assert s["invested"] == 2000 and s["net_profit"] == 100 and s["return_pct"] == 5.0
    assert s["twr_pct"] == pytest.approx(10.0, abs=0.01)                # +10% on the first $1,000, flat after
    assert 5.0 < s["xirr_pct"] < 10.0
    assert INV.xirr([(now, -100.0), (now + timedelta(days=365), 110.0)]) == pytest.approx(0.10, abs=1e-3)
    closed = [{"closed_at": "2026-02-28T10:00:00+00:00", "opened_at": "2026-02-28T09:00:00+00:00", "magic": 1001, "symbol": "EURUSD",
               "side": "buy", "volume": 0.1, "entry_price": 1.1, "exit_price": 1.101, "pnl": 10.0, "position_id": 1}]
    rep = R.summarize(closed, {"server": "Demo", "mode": "demo", "equity": 2100.0, "balance": 2100.0}, "weekly", now)
    assert rep["trades"] == 1 and rep["by_strategy"][0]["strategy"] == "EMA-1" and rep["disclaimer"]
    assert "EMA-1" in R.trades_csv(closed) and "<table>" in R.performance_html(rep, s, None, None)


def test_killswitch_command_needs_confirmation(rig, tmp_path):
    eng, gw, _ = rig
    h = CommandHandler(eng, lambda: {}, lambda: [], lambda: {}, lambda p: p, audit_path=str(tmp_path / "audit.log"))
    assert "CONFIRM" in h.handle("123", "/killswitch") and not eng.risk.halted
    assert "KILL SWITCH DONE" in h.handle("123", "/killswitch CONFIRM") and eng.risk.halted
    assert "CONFIRM" in h.handle("999", "/killswitch confirm")             # another chat has no pending confirmation
    assert (tmp_path / "audit.log").read_text().count("\n") == 3


def test_only_one_engine_loop_can_hold_the_lock(tmp_path):
    from app.api.trading import acquire_engine_lock
    first = acquire_engine_lock(str(tmp_path / "engine.lock"))
    assert first is not None
    import subprocess
    import sys
    code = ("import sys; sys.path.insert(0, '.'); from app.api.trading import acquire_engine_lock; "
            f"print(acquire_engine_lock(r'{tmp_path / 'engine.lock'}') is None)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert out.stdout.strip().endswith("True"), out.stderr[-400:]   # a second process is refused
    first.close()


def test_news_filter_blocks_entries_and_warns_once(rig):
    from app.risk.news import NewsCalendar, currencies
    eng, gw, t = rig
    at = (t["now"] + timedelta(minutes=35)).isoformat()
    feed = [{"title": "Non-Farm Employment Change", "country": "USD", "date": at, "impact": "High"},
            {"title": "Trade Balance", "country": "JPY", "date": at, "impact": "High"},
            {"title": "Speech", "country": "USD", "date": at, "impact": "Low"}]
    eng.news = NewsCalendar(str(eng.root), fetch=lambda: feed)
    assert currencies("XAUUSD") == {"USD"} and currencies("EURUSD") == {"EUR", "USD"}
    s = eng.add_session("TEST-BUY", "EURUSD", "M15")
    eng.set_status(s["id"], "running")
    eng.tick()                                              # baseline candle; news is 35 min away: no warning yet
    t["now"] += timedelta(minutes=15)                       # now 20 min before NFP: warn, and block the entry
    alerts = eng.tick()
    assert sum("NEWS" in a for a, _ in alerts) == 1 and "Non-Farm" in next(a for a, _ in alerts if "NEWS" in a)
    assert gw.sent == [] and "news blackout" in s["last_signal"]["decision"]
    t["now"] += timedelta(minutes=15)
    assert not any("NEWS" in a for a, _ in eng.tick())      # warned only once per event
    t["now"] += timedelta(minutes=45)                       # 40 min after the release: trading again
    eng.tick()
    assert len(gw.sent) == 1


def test_news_calendar_keeps_last_copy_when_fetch_fails(tmp_path):
    from app.risk.news import NewsCalendar
    now = datetime(2026, 11, 10, 12, tzinfo=UTC)
    good = NewsCalendar(str(tmp_path), fetch=lambda: [{"title": "CPI", "country": "USD", "date": now.isoformat(), "impact": "High"}])
    good.refresh(now)

    def boom():
        raise OSError("offline")
    bad = NewsCalendar(str(tmp_path), fetch=boom)
    bad.refresh(now + timedelta(hours=2))
    assert bad.error and len(bad.events) == 1 and bad.blackout("EURUSD", now, 30, 30, ["High"])["title"] == "CPI"
    assert bad.stale(now + timedelta(hours=13))


def test_gate2_evaluation_and_drills(rig, tmp_path):
    from app.gates import gate2
    eng, gw, t = rig
    s = eng.add_session("TEST-BUY", "EURUSD", "M15", mode="shakedown")
    eng.set_status(s["id"], "running")
    first = s["first_started_at"]
    eng.set_status(s["id"], "paused")
    eng.set_status(s["id"], "running")
    assert s["first_started_at"] == first                       # restarting does not reset the paper clock
    for k in range(6):
        eng.orders.append({"tag": f"rz:{k}", "client_id": str(k), "session_id": s["id"], "session_name": "x", "strategy": "TEST-BUY",
                           "symbol": "EURUSD", "side": "buy", "state": "closed", "placed_at": "2026-11-10T10:00:00+00:00",
                           "filled_at": "2026-11-10T10:15:00+00:00", "closed_at": "2026-11-10T14:15:00+00:00",
                           "pnl": 40.0 if k % 2 else -20.0, "risk_money": 20.0, "slippage_pips": 0.2, "spread_pips": 0.8,
                           "requested_price": 1.1, "lots": 0.1, "mode": "shakedown"})
    r = gate2.evaluate(eng, 10000.0, t["now"] + timedelta(weeks=9))
    ev = r["sessions"][0]
    assert ev["paper"]["trades"] == 6 and ev["paper"]["profit_factor"] == 2.0 and ev["paper"]["avg_hold_hours"] == 4.0
    crit = {c["criterion"]: c["status"] for c in ev["criteria"]}
    assert crit["Validated strategy (Gate 1)"] == "fail"         # shakedown sessions can never pass Gate 2
    assert crit["Duration"] == "pass" and crit["Trades"] == "pending" and crit["Failure drills (plan 11.4)"] == "pending"
    assert ev["verdict"] == "fail"
    d = gate2.Drills(str(eng.root))
    for k, _ in gate2.DRILLS:
        d.mark(k, True, "done in test")
    assert all(x["done"] for x in gate2.Drills(str(eng.root)).all())
    with pytest.raises(KeyError):
        d.mark("nope", True)


def test_news_failed_first_fetch_is_stale_and_retries_hourly(tmp_path):
    from app.risk.news import NewsCalendar
    now = datetime(2026, 11, 10, 12, tzinfo=UTC)
    calls = []

    def boom():
        calls.append(1)
        raise OSError("429 Too Many Requests")
    c = NewsCalendar(str(tmp_path), fetch=boom)
    c.refresh(now)
    c.refresh(now + timedelta(minutes=10))          # within the hour: no second attempt
    assert len(calls) == 1 and c.stale(now) and c.error.startswith("OSError")
    c.refresh(now + timedelta(minutes=61))
    assert len(calls) == 2
