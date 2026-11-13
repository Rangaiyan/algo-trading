"""Phase 4: strategy generator (genome operators, luck benchmark, end-to-end search + validation)."""
import random

import pandas as pd

from app.data import pipeline as P
from app.generate import genetic as G
from app.optimize import pipeline as OP
from app.strategies.rules import validate_spec


def test_genome_operators_always_produce_valid_distinct_specs():
    rng = random.Random(3)
    pop = [G.random_spec(rng) for _ in range(150)]
    for _ in range(300):
        a, b = rng.choice(pop), rng.choice(pop)
        pop.append(G.mutate(G.crossover(a, b, rng), rng, n=3))
    assert all(validate_spec(s) == [] for s in pop)
    assert all(s["setup"][0]["block"] == "structure_break" for s in pop)
    assert all(s["exit"]["stop"] != "sweep" or any(b["block"] == "liquidity_sweep" for b in s["setup"]) for s in pop)
    assert len({G.key(s) for s in pop}) > 400


def test_luck_benchmark_grows_with_candidates_and_shrinks_with_history():
    assert G.luck_sharpe(1, 3) == 0
    assert G.luck_sharpe(1000, 3) > G.luck_sharpe(30, 3) > 0
    assert G.luck_sharpe(100, 10) < G.luck_sharpe(100, 2)


def test_generate_end_to_end_on_synthetic(monkeypatch):
    df = P.synthetic(days=240)
    hold = df.index[int(len(df) * 0.9)]
    ins = df[df.index < hold]
    cut = ins.index[int(len(ins) * 0.75)]
    split = {"df": df, "meta": {"holdout_start": str(hold), "data_version": "syn"}, "insample": ins,
             "train": ins[ins.index < cut], "valid": ins[ins.index >= cut], "holdout": df[df.index >= hold]}
    monkeypatch.setattr(OP, "load_split", lambda symbol, timeframe: split)
    monkeypatch.setattr(OP, "MIN_TRAIN_TRADES", 5)
    job = OP.Job()
    r = G.generate("EURUSD", "M15", population=6, generations=2, survivors=1, job=job)
    assert r["evaluated"] >= 6 and len(r["curve"]) == 2 and r["luck_sharpe"] > 0
    assert r["curve"][1]["best"] >= r["curve"][0]["best"]  # elitism: never worse
    assert r["leaderboard"] == sorted(r["leaderboard"], key=lambda c: c["score"], reverse=True)
    if r["survivors"]:
        rep = r["survivors"][0]["report"]
        assert rep["gate1"][0]["criterion"].startswith("Beats the multiple-testing")
        assert rep["verdict"] in ("pass", "fail", "pending")
    assert job.stage == "done" and job.done >= r["evaluated"]


def test_generate_stops_when_cancelled(monkeypatch):
    df = P.synthetic(days=120)
    split = {"df": df, "meta": {"holdout_start": str(df.index[-1]), "data_version": "syn"}, "insample": df,
             "train": df, "valid": df.iloc[-500:], "holdout": df.iloc[-10:]}
    monkeypatch.setattr(OP, "load_split", lambda symbol, timeframe: split)
    job = OP.Job()
    job.cancelled = True
    r = G.generate("EURUSD", "M15", population=6, generations=3, survivors=2, job=job)
    assert r["evaluated"] == 0 and r["survivors"] == []
    assert isinstance(pd.Timestamp(r["train_period"][0]), pd.Timestamp)
