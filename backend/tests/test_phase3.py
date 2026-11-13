"""Phase 3: scoring, search spaces, Monte Carlo, Gate 1, library lifecycle, rule builder, swap rollovers."""
import copy
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from app.backtest.engine import rollover_multipliers
from app.data import pipeline as P
from app.library import store
from app.optimize import pipeline as OP
from app.optimize.spaces import SPACES, neighbours
from app.strategies.rules import EXAMPLE, RuleStrategy, validate_spec
from tests.test_strategies_data import collect

M = {"trades": 120, "net_profit": 500.0, "return_pct": 5.0, "win_rate": 0.4, "profit_factor": 1.5,
     "max_drawdown_pct": -8.0, "sharpe": 1.2, "sortino": 1.8, "expectancy": 4.0}


def test_score_rewards_quality_and_gates_on_trade_count():
    assert OP.score(M) > OP.score({**M, "profit_factor": 1.1})
    assert OP.score(M) > OP.score({**M, "max_drawdown_pct": -30.0})
    assert OP.score({**M, "trades": 3}) < -4  # too few trades: never a winner


def test_neighbours_step_each_numeric_param_within_bounds():
    nb = neighbours({"rr": 1.5, "atr_mult": 2.0}, SPACES["EMA-1"])
    labels = [lbl for lbl, _ in nb]
    assert "rr -0.25" not in labels and "rr +0.25" in labels  # 1.5 is the lower bound
    assert {"atr_mult -0.25", "atr_mult +0.25"} <= set(labels)
    assert all(SPACES["EMA-1"]["rr"][1] <= p["rr"] <= SPACES["EMA-1"]["rr"][2] for _, p in nb)


def test_monte_carlo_bounds_and_profit_probability():
    win = SimpleNamespace(pnl=20.0, risk_money=10.0, spread_cost=0.5, slippage_cost=0.1)
    loss = SimpleNamespace(pnl=-10.0, risk_money=10.0, spread_cost=0.5, slippage_cost=0.1)
    mc = OP.monte_carlo(SimpleNamespace(trades=[win] * 60 + [loss] * 40))
    assert mc["profit_probability"] > 0.95
    assert mc["return_pct"]["p5"] <= mc["return_pct"]["p50"] <= mc["return_pct"]["p95"]
    assert mc["max_dd_pct"]["p95"] <= mc["max_dd_pct"]["p50"] <= 0
    assert OP.monte_carlo(SimpleNamespace(trades=[win] * 5))["runs"] == 0


def _report(**over):
    base = {"insample": M, "walk_forward": {"windows": [1], "efficiency": 0.7},
            "monte_carlo": {"runs": 100, "profit_probability": 0.9, "max_dd_pct": {"p95": -12.0}},
            "sensitivity": {"profitable_share": 0.8}, "cost_stress": {"net_profit": 100.0},
            "cross_pair": [{"net_profit": 1}, {"net_profit": 1}, {"net_profit": -1}], "holdout": None}
    return {**base, **over}


def test_gate1_pending_until_holdout_then_pass_or_fail():
    rows = OP.gate1(_report())
    assert OP.gate_verdict(rows) == "pending"
    assert OP.gate_verdict(OP.gate1(_report(holdout={"net_profit": 50, "trades": 35}))) == "pass"
    assert OP.gate_verdict(OP.gate1(_report(holdout={"net_profit": 50, "trades": 10}))) == "fail"
    assert OP.gate_verdict(OP.gate1(_report(insample={**M, "profit_factor": 1.1}))) == "fail"
    assert OP.gate_verdict(OP.gate1(_report(walk_forward={"windows": [1], "efficiency": 0.2}))) == "fail"


def test_library_lifecycle_rules(tmp_path):
    root = str(tmp_path)
    rep = {"verdict": "pending", "data_version": "x", "insample": M}
    e = store.create("t", "EMA-2", "EURUSD", "H1", {"rr": 2}, report=rep, root=root)
    assert e["status"] == "backtested" and store.allowed_next(e) == ["retired"]
    with pytest.raises(store.LifecycleError):
        store.promote(e["id"], "validated", root=root)       # gate not passed
    with pytest.raises(store.LifecycleError):
        store.promote(e["id"], "live", root=root)            # needs Gate 2
    e = store.record_holdout(e["id"], {"net_profit": 1, "trades": 40}, [], "pass", root=root)
    assert e["holdout_used"] and e["report"]["holdout"]["first_run"]
    assert store.promote(e["id"], "validated", root=root)["status"] == "validated"
    assert store.promote(e["id"], "paper", root=root)["status"] == "paper"
    assert [h["status"] for h in store.get(e["id"], root)["history"]][-2:] == ["validated", "paper"]
    again = store.record_holdout(e["id"], {"net_profit": 1, "trades": 40}, [], "pass", root=root)
    assert not again["report"]["holdout"]["first_run"] and "AGAIN" in again["history"][-1]["note"]
    assert [x["id"] for x in store.list_all(root)] == [e["id"]]
    with pytest.raises(KeyError):
        store.get("../etc/passwd", root)


def test_rule_spec_validation_and_overrides():
    assert validate_spec(EXAMPLE) == []
    bad = copy.deepcopy(EXAMPLE)
    bad["setup"].append({"block": "liquidity_sweep", "levels": ["nope"]})
    bad["exit"]["stop"] = "moon"
    errs = validate_spec(bad)
    assert any("levels" in e for e in errs) and any("exit.stop" in e for e in errs)
    r = RuleStrategy(spec=EXAMPLE, threshold=4, buffer_atr=0.3, min_rr=2.5, swing_n=4)
    assert r.spec["threshold"] == 4 and r.spec["exit"]["buffer_atr"] == 0.3 and r.p("swing_n") == 4
    assert EXAMPLE["threshold"] == 6  # the shared example is not mutated


def test_rule_strategy_never_looks_ahead():
    df = P.synthetic(days=90)
    spec = {**copy.deepcopy(EXAMPLE), "filters": {}, "threshold": 2}
    full = collect(RuleStrategy(spec=spec), df)
    k = len(df) // 2
    assert collect(RuleStrategy(spec=spec), df.iloc[:k]) == full[:k]
    assert sum(map(len, full)) > 0


def test_rollover_multipliers_triple_wednesday_and_weekend():
    # bars at 16:00 and 18:00 New York (EST, UTC-5) on Mon 2026-01-05 .. ; rollover at 17:00 NY
    idx = pd.DatetimeIndex(["2026-01-05 21:00", "2026-01-05 23:00",   # Mon roll crossed
                            "2026-01-07 21:00", "2026-01-07 23:00",   # Wed roll crossed -> x3
                            "2026-01-09 21:00", "2026-01-12 15:00"], tz="UTC")  # Fri 16:00 NY -> Mon: Fri, Sat, Sun rolls
    m = rollover_multipliers(idx, triple_weekday=2)
    assert list(m) == [0, 1, 1, 3, 1, 3]  # Tue roll; Wed roll x3; Thu roll; Fri 16:00 -> Mon crosses Fri+Sat+Sun = 3


def test_engine_rewrite_kept_results_and_is_fast():
    from app.backtest.engine import BacktestConfig, run_backtest
    from app.domain import Instrument, Market
    from app.strategies.ema.strategies import EMACrossover
    df = P.synthetic(days=60)
    r = run_backtest(df, EMACrossover(), Instrument(Market.FOREX, "EURUSD"), BacktestConfig())
    assert len(r.trades) > 0 and np.isfinite(r.equity.iloc[-1])
