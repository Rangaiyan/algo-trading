from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.ledger import analytics, build
from app.main import app

client = TestClient(app)


def row(pnl, exit_ts, side="buy", symbol="EURUSD", desk="ema", pips=None):
    return {"pnl": pnl, "exit_ts": exit_ts, "side": side, "symbol": symbol, "desk": desk,
            "pips": pnl / 10 if pips is None else pips, "spread_cost": 1.0, "slippage_cost": 0.5, "commission": 0.0,
            "swap": 0.0, "mfe_pips": 20.0, "mae_pips": 10.0, "r_multiple": pnl / 100}


# Tue 10 Nov: +100, -50 · Wed 11 Nov: +200 · Thu 12 Nov: -300   (2026, all mid-day New York)
TRADES = [row(100, "2026-11-10T15:00:00+00:00"), row(-50, "2026-11-10T18:00:00+00:00", side="sell"),
          row(200, "2026-11-11T15:00:00+00:00"), row(-300, "2026-11-12T15:00:00+00:00", side="sell")]


def test_trading_day_rolls_at_1700_new_york():
    assert analytics.trading_day("2026-11-15T22:30:00+00:00") == date(2026, 11, 16)   # Sun 17:30 NY -> Monday
    assert analytics.trading_day("2026-11-13T21:59:00+00:00") == date(2026, 11, 13)   # Fri 16:59 NY -> Friday
    assert analytics.trading_day("2026-07-15T21:30:00+00:00") == date(2026, 7, 16)    # summer: 17:30 EDT -> next day


def test_dashboard_hand_calc():
    d = analytics.dashboard([dict(t) for t in TRADES], initial_capital=10_000)
    c, k = d["career"], d["kpis"]
    assert c["pnl"] == -50 and c["trades"] == 4 and c["trading_days"] == 3 and c["since"] == "2026-11-10"
    assert c["avg_day"] == pytest.approx(-16.67, abs=0.01)
    assert k["win_rate"] == 0.5 and k["wins"] == 2 and k["losses"] == 2
    assert k["profit_factor"] == pytest.approx(300 / 350, abs=0.001)
    assert k["best_day"] == {"pnl": 200, "date": "2026-11-11"} and k["worst_day"] == {"pnl": -300, "date": "2026-11-12"}
    assert k["high_water"] == {"pnl": 250, "date": "2026-11-11"}          # 50, 250, -50 cumulative
    assert k["deepest_dip"] == -300 and k["lowest"] == {"pnl": -50, "date": "2026-11-12"}
    assert k["streak"] == -1 and k["best_win_run"] == 1 and k["worst_loss_run"] == 1
    assert k["max_loss"]["pnl"] == -300
    assert k["costs"] == pytest.approx(6.0) and k["gross_before_costs"] == pytest.approx(-44.0)
    assert k["long_pnl"] == 300 and k["short_pnl"] == -350
    assert d["today"]["date"] == "2026-11-12" and d["today"]["pnl"] == -300 and d["today"]["kept_pct"] is None
    assert d["week"]["pnl"] == -50 and d["week"]["vs_last"] == -50
    assert [w["pnl"] for w in d["weeks_last_12"]] == [-50]
    assert d["equity"][-1]["equity"] == 9_950


def test_empty_dashboard_is_flagged_not_faked():
    assert analytics.dashboard([], 10_000)["empty"] is True


@pytest.fixture(scope="module")
def small_ledger():
    return build.build_ledger(days=40, symbols=["EURUSD"], start="2026-01-05")


def test_built_ledger_reconciles_per_trade(small_ledger):
    assert small_ledger["source"] == "demo-synthetic" and len(small_ledger["sessions"]) == 3
    ts = small_ledger["trades"]
    assert ts and len({t["id"] for t in ts}) == len(ts)
    for t in ts:
        recon = t["gross_pnl"] - t["spread_cost"] - t["slippage_cost"] - t["commission"] - t["swap"]
        assert t["pnl"] == pytest.approx(recon, abs=0.05)
        assert t["mfe_pips"] >= 0 and t["mae_pips"] >= 0 and t["desk"] in build.DESKS
        assert t["session_id"] in {s["id"] for s in small_ledger["sessions"]}


def test_ledger_api_filters(monkeypatch, small_ledger):
    monkeypatch.setattr(build, "load_ledger", lambda days=150, symbols=None, rebuild=False: small_ledger)
    d = client.get("/ledger/dashboard").json()
    assert d["source"] == "demo-synthetic" and d["account"] is None and d["sessions"] == 3
    assert d["career"]["trades"] == len(small_ledger["trades"])
    only = client.get("/ledger/dashboard", params={"desk": "candle"}).json()
    assert only["sessions"] == 1 and only["career"]["trades"] < d["career"]["trades"]
    assert client.get("/ledger/dashboard", params={"desk": "smc"}).json()["empty"] is True   # no SMC strategies yet
    page = client.get("/ledger/trades", params={"limit": 5}).json()
    assert len(page["trades"]) == 5 and page["total"] == len(small_ledger["trades"])
    assert page["trades"][0]["exit_ts"] >= page["trades"][1]["exit_ts"]
    assert len(client.get("/ledger/sessions").json()["sessions"]) == 3


# ---------------- desk pages: session metrics, lifecycle, enrichment, chart, filters ----------------
from app.ledger import sessions as S


def srow(pnl, entry, exit_):
    return {"pnl": pnl, "entry_ts": entry, "exit_ts": exit_, "pips": pnl / 10}


def test_session_metrics_hand_calc():
    m = S.session_metrics([
        srow(100, "2026-11-10T14:00:00+00:00", "2026-11-10T15:00:00+00:00"),
        srow(-50, "2026-11-09T14:00:00+00:00", "2026-11-09T15:00:00+00:00"),
        srow(-30, "2026-11-11T14:00:00+00:00", "2026-11-11T15:00:00+00:00"),
    ])
    assert (m["net"], m["trades"], m["wins"], m["losses"]) == (20, 3, 1, 2)
    assert (m["peak"], m["low"]) == (50, -50)               # cumulative: -50, 50, 20
    assert m["per_trade"] == pytest.approx(6.67, abs=0.01) and m["win_pct"] == pytest.approx(0.3333, abs=1e-4)
    assert m["today"] == {"date": "2026-11-11", "pnl": -30, "wins": 0, "losses": 1}
    assert m["prev_day"]["date"] == "2026-11-10" and m["prev_day"]["pnl"] == 100
    assert m["since"] == "2026-11-09T14:00:00+00:00"
    assert S.session_metrics([])["trades"] == 0


def full_trade(**over):
    t = {"id": 1, "side": "buy", "symbol": "EURUSD", "entry_px": 1.1000, "exit_px": 1.1020, "stop_loss": 1.0990, "take_profit": 1.1030,
         "pips": 20.0, "pnl": 190.0, "commission": 7.0, "swap": 3.0, "spread_cost": 0.0, "slippage_cost": 0.0, "mfe_money": 250.0,
         "mfe_pips": 25.0, "mae_pips": 5.0, "entry_ts": "2026-11-11T15:00:00+00:00", "exit_ts": "2026-11-11T15:45:00+00:00"}
    t.update(over)
    return t


def test_enrich_trade_hand_calc():
    e = S.enrich_trade(full_trade())
    assert e["given_back"] == 50 and e["kept_pct"] == 80 and e["peak_profit"] == 250    # price pnl 200 of best 250
    assert e["held_minutes"] == 45 and e["overnight"] is False
    assert e["best_price"] == pytest.approx(1.1025) and e["worst_price"] == pytest.approx(1.0995)
    assert e["pip_size"] == 0.0001 and e["stop_pips"] == 10.0 and e["target_pips"] == 30.0
    assert e["planned_rr"] == 3.0 and e["capture"] == pytest.approx(0.8) and e["total_costs"] == 10
    short = S.enrich_trade(full_trade(side="sell", entry_px=1.1020, exit_px=1.1000, stop_loss=1.1030, take_profit=1.0990))
    assert short["best_price"] == pytest.approx(1.1020 - 25 * 0.0001) and short["worst_price"] == pytest.approx(1.1020 + 5 * 0.0001)
    assert S.enrich_trade(full_trade(exit_ts="2026-11-11T23:00:00+00:00"))["overnight"] is True   # crossed 17:00 NY roll
    assert S.enrich_trade(full_trade(pnl=-100.0, mfe_money=0.0))["kept_pct"] == 0


def test_lifecycle_transitions(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "STATE_PATH", tmp_path / "state.json")
    s = {"id": "x", "status": "running"}
    assert S.apply_action(s, "pause") == "paused"
    with pytest.raises(S.InvalidTransition):
        S.apply_action(s, "pause")
    with pytest.raises(S.InvalidTransition):
        S.apply_action(s, "archive")                        # cannot archive while not stopped
    assert S.apply_action(s, "resume") == "running"
    assert S.apply_action(s, "stop") == "stopped" and S.apply_action(s, "archive") == "archived"
    with pytest.raises(S.InvalidTransition):
        S.apply_action(s, "resume")
    with pytest.raises(S.InvalidTransition):
        S.apply_action(s, "explode")


@pytest.fixture
def api(monkeypatch, small_ledger, tmp_path):
    monkeypatch.setattr(build, "load_ledger", lambda days=150, symbols=None, rebuild=False: small_ledger)
    monkeypatch.setattr(S, "STATE_PATH", tmp_path / "state.json")
    return client


def test_session_api_lifecycle_and_archive_visibility(api, small_ledger):
    sid = small_ledger["sessions"][0]["id"]
    listing = api.get("/ledger/sessions").json()
    assert len(listing["sessions"]) == 3 and "metrics" in listing["sessions"][0] and listing["as_of"]
    assert api.post(f"/ledger/sessions/{sid}/pause").json()["status"] == "paused"
    assert api.post(f"/ledger/sessions/{sid}/pause").status_code == 409
    assert api.post(f"/ledger/sessions/{sid}/archive").status_code == 409
    api.post(f"/ledger/sessions/{sid}/stop")
    api.post(f"/ledger/sessions/{sid}/archive")
    assert len(api.get("/ledger/sessions").json()["sessions"]) == 2                     # archived hidden by default
    assert len(api.get("/ledger/sessions", params={"include_archived": True}).json()["sessions"]) == 3
    assert api.get("/ledger/sessions", params={"status": "archived"}).json()["sessions"][0]["id"] == sid
    assert api.post("/ledger/sessions/nope/pause").status_code == 404


def test_chart_has_ordered_candles_and_valid_markers(api, small_ledger):
    s = small_ledger["sessions"][0]
    mine = [t for t in small_ledger["trades"] if t["session_id"] == s["id"]]
    assert mine
    d = api.get(f"/ledger/sessions/{s['id']}/chart", params={"bars": 300}).json()
    times = [c["time"] for c in d["candles"]]
    assert times == sorted(times) and len(times) <= 300 and d["last_price"] == d["candles"][-1]["close"]
    assert all(times[0] <= m["time"] <= times[-1] for m in d["markers"])
    target = mine[len(mine) // 2]
    around = api.get(f"/ledger/sessions/{s['id']}/chart", params={"around": target["id"], "bars": 200}).json()
    assert any(m["trade_id"] == target["id"] and m["kind"] == "entry" for m in around["markers"])
    assert api.get(f"/ledger/sessions/{s['id']}/chart", params={"around": 999999}).status_code == 404


def test_trade_filters_and_detail(api, small_ledger):
    allt = api.get("/ledger/trades", params={"limit": 5000}).json()
    assert allt["total"] == len(small_ledger["trades"])
    wins = api.get("/ledger/trades", params={"result": "win", "limit": 5000}).json()
    assert wins["total"] and all(t["pnl"] > 0 for t in wins["trades"])
    buys = api.get("/ledger/trades", params={"side": "buy", "limit": 5000}).json()
    assert all(t["side"] == "buy" for t in buys["trades"]) and buys["total"] < allt["total"]
    one = allt["trades"][0]
    day = api.get("/ledger/trades", params={"day": __import__("app.ledger.analytics", fromlist=["x"]).trading_day(one["exit_ts"]).isoformat(), "limit": 5000}).json()
    assert one["id"] in {t["id"] for t in day["trades"]}
    tp = api.get("/ledger/trades", params={"q": "tp", "limit": 5000}).json()
    assert tp["total"] and all("tp" in t["exit_reason"] or "tp" in t["symbol"].lower() + t["strategy"].lower() for t in tp["trades"])
    d = api.get(f"/ledger/trades/{one['id']}").json()
    assert d["trade"]["id"] == one["id"] and "given_back" in d["trade"] and d["session"]["id"] == one["session_id"]
    assert api.get("/ledger/trades/99999999").status_code == 404
    assert api.get("/ledger/trades", params={"result": "maybe"}).status_code == 422


def test_enrich_uses_instrument_pip_size_even_for_zero_pip_trades():
    jpy = S.enrich_trade(full_trade(symbol="USDJPY", entry_px=150.00, exit_px=150.00, stop_loss=149.90, take_profit=150.30, pips=0.0, mfe_pips=12.0, mae_pips=4.0))
    assert jpy["pip_size"] == 0.01 and jpy["stop_pips"] == 10.0
    assert jpy["best_price"] == pytest.approx(150.12) and jpy["worst_price"] == pytest.approx(149.96)
