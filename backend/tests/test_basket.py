"""Basket validation: combined equity/trades and the full pipeline on synthetic pairs."""
import pandas as pd
import pytest

from app.backtest.engine import BacktestConfig, run_backtest
from app.data import pipeline as P
from app.domain import Instrument, Market
from app.optimize import basket as B
from app.optimize import pipeline as OP
from app.strategies.ema.strategies import EMACrossover


def test_combine_sums_pnl_on_one_account():
    cfg = BacktestConfig()
    a = run_backtest(P.synthetic(days=60, seed=1), EMACrossover(), Instrument(Market.FOREX, "EURUSD"), cfg)
    b = run_backtest(P.synthetic(days=60, seed=2), EMACrossover(), Instrument(Market.FOREX, "EURUSD"), cfg)
    c = B.combine([a, b])
    assert len(c.trades) == len(a.trades) + len(b.trades)
    assert c.equity.iloc[-1] == pytest.approx(a.equity.iloc[-1] + b.equity.iloc[-1] - cfg.initial_balance)
    assert list(c.trades) == sorted(c.trades, key=lambda t: t.exit_ts)


def test_basket_pipeline_end_to_end(monkeypatch):
    def split(seed):
        df = P.synthetic(days=420, seed=seed)
        hold = df.index[int(len(df) * 0.9)]
        ins = df[df.index < hold]
        cut = ins.index[int(len(ins) * 0.75)]
        return {"df": df, "meta": {"holdout_start": str(hold), "data_version": f"s{seed}"}, "insample": ins,
                "train": ins[ins.index < cut], "valid": ins[ins.index >= cut], "holdout": df[df.index >= hold]}
    splits = {"EURUSD": split(3), "GBPUSD": split(4), "USDJPY": split(5), "AUDUSD": split(6), "XAUUSD": split(7)}
    monkeypatch.setattr(OP, "load_split", lambda s, tf: splits[s])
    r = B.run_basket_pipeline("EMA-2", ["EURUSD", "GBPUSD"], "M15", trials=4, wf_trials=2, wf_train_months=6, wf_test_months=3)
    assert r["basket"] and r["symbol"] == "EURUSD+GBPUSD"
    assert r["insample"]["trades"] == sum(m["trades"] for m in r["members"]["insample"].values())
    assert r["gate1"][1]["criterion"] == "Not carried by one pair"
    assert {p["symbol"] for p in r["cross_pair"]} == set(splits) and r["walk_forward"]["windows"]
    h = B.run_basket_holdout("EMA-2", ["EURUSD", "GBPUSD"], "M15", r["params"])
    assert set(h["members"]) == {"EURUSD", "GBPUSD"} and isinstance(pd.Timestamp(h["period"][0]), pd.Timestamp)
