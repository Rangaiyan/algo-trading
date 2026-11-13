"""Basket validation: ONE rule set with the SAME settings traded on several pairs, judged on the combined result.

Why: a selective strategy can be sound but trade too rarely on one pair to reach the plan's 100-trade minimum.
Running it on a basket gives enough trades without loosening any Gate 1 threshold, and because the settings are
tuned on the basket's COMBINED training data (never per pair) it avoids cherry-picking each pair's best settings.

Combined equity = starting balance + the sum of each pair's P&L (all pairs trade one account, each trade risking
the configured % of the starting balance). Every Gate 1 check runs on the combined trades; the report also shows
each pair's own result so a basket carried by one pair is visible.
"""
from __future__ import annotations

from types import SimpleNamespace

import optuna
import pandas as pd

from app.backtest.metrics import compute_metrics
from app.data.mt5_history import SYMBOLS
from app.optimize import pipeline as OP
from app.optimize.spaces import SPACES, neighbours, suggest


def combine(results: list) -> SimpleNamespace:
    init = results[0].config.initial_balance
    idx = results[0].equity.index
    for r in results[1:]:
        idx = idx.union(r.equity.index)
    total = pd.Series(init, index=idx, dtype=float)
    for r in results:
        total += (r.equity - init).reindex(idx).ffill().fillna(0.0)
    trades = sorted((t for r in results for t in r.trades), key=lambda t: t.exit_ts)
    return SimpleNamespace(trades=trades, equity=total, config=results[0].config)


def _slice(df: pd.DataFrame, start=None, end=None) -> pd.DataFrame:
    if start is not None:
        df = df[df.index >= start]
    if end is not None:
        df = df[df.index < end]
    return df


def bt_basket(strategy: str, splits: dict, part: str, params: dict, stress: float = 1.0, start=None, end=None):
    per = {}
    for sym, sp in splits.items():
        df = _slice(sp[part], start, end)
        if len(df) < 300:
            continue
        per[sym] = OP.bt(strategy, sym, df, sp["meta"], params, stress)
    if not per:
        raise ValueError("no pair has enough data in that period")
    comb = combine([r for r, _ in per.values()])
    return comb, compute_metrics(comb), {s: OP.slim(m) for s, (_, m) in per.items()}


def optimise_basket(strategy, splits, trials, job=None, seed=7, base=None, start=None, end=None, part="train"):
    base = base or {}
    if trials <= 0:
        _, m, _ = bt_basket(strategy, splits, part, base, start=start, end=end)
        return {}, OP.score(m), []
    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed))
    history = []

    def objective(trial):
        if job and job.cancelled:
            raise optuna.TrialPruned()
        p = suggest(trial, SPACES[strategy])
        trial.set_user_attr("params", p)
        _, m, _ = bt_basket(strategy, splits, part, {**base, **p}, start=start, end=end)
        s = OP.score(m)
        history.append({"trial": trial.number, "score": round(s, 4), **OP.slim(m)})
        if job:
            job.step()
        return s

    study.optimize(objective, n_trials=trials, catch=(ValueError,))
    return study.best_trial.user_attrs["params"], study.best_trial.value, history


def run_basket_pipeline(strategy: str, symbols: list[str], timeframe: str, trials: int = 60, walk_forward_on: bool = True,
                        wf_train_months: int = 12, wf_test_months: int = 3, wf_trials: int = 15,
                        job: OP.Job | None = None, base: dict | None = None) -> dict:
    job = job or OP.Job()
    base = base or {}
    if trials <= 0:
        wf_trials = 0
    splits = {s: OP.load_split(s, timeframe) for s in symbols}
    ref = splits[symbols[0]]
    ins_start = max(sp["insample"].index[0] for sp in splits.values())
    ins_end = min(sp["insample"].index[-1] for sp in splits.values())
    months = (ins_end - ins_start).days / 30.4
    wf_windows = max(0, int((months - wf_train_months) // wf_test_months))
    job.total += trials + (wf_windows * (wf_trials + 1) if walk_forward_on else 0) + 2 * len(SPACES[strategy]) + 6

    job.stage = f"optimising the basket on training data ({'+'.join(symbols)})"
    tuned, best_score, history = optimise_basket(strategy, splits, trials, job, base=base)
    best = {**base, **tuned}

    job.stage = "validating the basket"
    _, m_train, per_train = bt_basket(strategy, splits, "train", best)
    _, m_valid, per_valid = bt_basket(strategy, splits, "valid", best)
    res_ins, m_ins, per_ins = bt_basket(strategy, splits, "insample", best)
    _, m_def, _ = bt_basket(strategy, splits, "insample", base)
    job.step("basket in-sample backtests done")

    wf = None
    if walk_forward_on:
        job.stage = "walk-forward (basket)"
        rows, start = [], ins_start
        while True:
            tr_end = start + pd.DateOffset(months=wf_train_months)
            te_end = tr_end + pd.DateOffset(months=wf_test_months)
            if te_end > ins_end + pd.Timedelta(days=7):
                break
            try:
                p, _, _ = optimise_basket(strategy, splits, wf_trials, job, seed=len(rows) + 1, base=base,
                                          start=start, end=tr_end, part="insample")
                full = {**base, **p}
                _, mi, _ = bt_basket(strategy, splits, "insample", full, start=start, end=tr_end)
                _, mo, _ = bt_basket(strategy, splits, "insample", full, start=tr_end, end=te_end)
                rows.append({"train": [str(start)[:10], str(tr_end)[:10]], "test": [str(tr_end)[:10], str(te_end)[:10]],
                             "params": p, "in": OP.slim(mi), "out": OP.slim(mo)})
                job.step(f"basket walk-forward window {len(rows)}: test {str(tr_end)[:10]} -> {mo['return_pct']}%")
            except ValueError:
                pass
            start += pd.DateOffset(months=wf_test_months)
        ann_in = sum(r["in"]["return_pct"] * 12 / wf_train_months for r in rows) / len(rows) if rows else 0.0
        ann_out = sum(r["out"]["return_pct"] * 12 / wf_test_months for r in rows) / len(rows) if rows else 0.0
        wf = {"windows": rows, "annual_in_pct": round(ann_in, 2), "annual_out_pct": round(ann_out, 2),
              "efficiency": round(ann_out / ann_in, 3) if ann_in > 0 else 0.0,
              "oos_trades": sum(r["out"]["trades"] for r in rows), "oos_profitable_windows": sum(r["out"]["net_profit"] > 0 for r in rows)}

    job.stage = "Monte Carlo, sensitivity, cost stress, other pairs (basket)"
    mc = OP.monte_carlo(res_ins)
    sens_rows = []
    for label, p in neighbours({**OP._space_defaults(strategy, best), **tuned}, SPACES[strategy]):
        _, m, _ = bt_basket(strategy, splits, "insample", {**{k: v for k, v in best.items() if k not in tuned}, **p})
        sens_rows.append({"change": label, **OP.slim(m)})
        job.step()
    prof = [r for r in sens_rows if r["net_profit"] > 0]
    sens = {"neighbours": sens_rows, "profitable_share": round(len(prof) / len(sens_rows), 3) if sens_rows else None,
            "worst_pf": min((r["profit_factor"] or 0 for r in sens_rows), default=None)}
    _, m_stress, _ = bt_basket(strategy, splits, "insample", best, stress=1.5)
    # every pair on its own, members and non-members (non-members are a true out-of-basket test)
    pairs = [{"symbol": s, "is_target": s in symbols, **per_ins[s]} for s in symbols if s in per_ins]
    for other in [s for s in SYMBOLS if s not in symbols]:
        try:
            sp = OP.load_split(other, timeframe)
            _, m = OP.bt(strategy, other, sp["insample"], sp["meta"], best)
            pairs.append({"symbol": other, "is_target": False, **OP.slim(m)})
        except FileNotFoundError:
            continue
    job.step("cost stress and other pairs done")

    name = "+".join(symbols)
    report = {
        "strategy": strategy, "symbol": name, "symbols": symbols, "basket": True, "timeframe": timeframe, "params": best,
        "tuned": tuned, "split": {"train": OP.period(ref["train"]), "validation": OP.period(ref["valid"]), "holdout": OP.period(ref["holdout"])},
        "data_version": "+".join(sp["meta"]["data_version"] for sp in splits.values()), "trials": trials,
        "best_score": round(best_score, 4), "history": history, "train": OP.slim(m_train), "validation": OP.slim(m_valid),
        "insample": OP.slim(m_ins), "defaults_insample": OP.slim(m_def), "walk_forward": wf, "monte_carlo": mc,
        "sensitivity": sens, "cost_stress": OP.slim(m_stress), "cross_pair": pairs, "holdout": None,
        "members": {"train": per_train, "validation": per_valid, "insample": per_ins},
        "multiple_testing_note": f"{trials} parameter sets were tried on the basket's combined training data; settings are shared "
                                 "by every pair (never tuned per pair). Trust validation, walk-forward and the hold-out.",
    }
    report["gate1"] = OP.gate1(report)
    carried = [s for s, m in per_ins.items() if m["net_profit"] > 0]
    report["gate1"].insert(1, {"criterion": "Not carried by one pair", "status": "pass" if len(carried) >= 2 else "fail",
                               "value": f"{len(carried)} of {len(per_ins)} basket pairs profitable in-sample",
                               "required": ">= 2 basket pairs profitable"})
    report["verdict"] = OP.gate_verdict(report["gate1"])
    job.stage = "done"
    return report


def run_basket_holdout(strategy: str, symbols: list[str], timeframe: str, params: dict) -> dict:
    splits = {s: OP.load_split(s, timeframe) for s in symbols}
    _, m, per = bt_basket(strategy, splits, "holdout", params)
    ref = splits[symbols[0]]
    return {"period": OP.period(ref["holdout"]), **OP.slim(m), "members": per}
