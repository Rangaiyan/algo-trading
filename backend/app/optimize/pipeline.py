"""Optimise on training data only, then validate (doc 9.3, 10.5, 10.6).

Data split (per symbol/timeframe):
    |------ in-sample (everything before the hold-out) ------|-- hold-out (last 6 months) --|
    |------- train (first 75%) -------|-- validation (25%) --|
The optimiser only ever sees TRAIN. Validation, walk-forward, sensitivity, cost stress and cross-pair use the
in-sample data. The hold-out is run separately, once, from the strategy library.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import optuna
import pandas as pd

from app.backtest import runner
from app.backtest.metrics import compute_metrics
from app.data import pipeline as P
from app.data.mt5_history import SYMBOLS, read_meta
from app.optimize.spaces import SPACES, neighbours, suggest

optuna.logging.set_verbosity(optuna.logging.WARNING)

TRAIN_SHARE = 0.75
MIN_TRAIN_TRADES = 30
GATE = {"min_trades": 100, "min_holdout_trades": 30, "min_pf": 1.3, "max_dd_pct": 15.0, "min_sharpe": 1.0,
        "min_sortino": 1.5, "min_wfe": 0.5, "min_neighbour_share": 0.7, "mc_min_profit_prob": 0.8,
        "min_profitable_pairs": 2}


@dataclass
class Job:
    """Progress handle shared with the API thread."""
    stage: str = "starting"
    done: int = 0
    total: int = 0
    log: list[str] = field(default_factory=list)
    cancelled: bool = False

    def step(self, msg: str | None = None):
        self.done += 1
        if msg:
            self.log.append(msg)


# ---------------- data ----------------

def load_split(symbol: str, timeframe: str) -> dict:
    df = P.read_store(runner.DATA_ROOT, symbol, timeframe)
    meta = read_meta(runner.DATA_ROOT, symbol, timeframe)
    if not meta:
        raise FileNotFoundError(f"no meta for {symbol} {timeframe}; download the data first")
    hold_at = pd.Timestamp(meta["holdout_start"])
    ins, hold = df[df.index < hold_at], df[df.index >= hold_at]
    cut = ins.index[int(len(ins) * TRAIN_SHARE)]
    return {"df": df, "meta": meta, "insample": ins, "train": ins[ins.index < cut], "valid": ins[ins.index >= cut],
            "holdout": hold}


def period(df: pd.DataFrame) -> list[str]:
    return [str(df.index[0])[:10], str(df.index[-1])[:10]] if len(df) else [None, None]


# ---------------- scoring ----------------

def score(m: dict, min_trades: int = MIN_TRAIN_TRADES) -> float:
    """Composite objective (doc 9.3): risk-adjusted, drawdown-penalised, trade-count gated. Not raw profit."""
    if m["trades"] < min_trades:
        return -5.0 + m["trades"] / min_trades
    pf = m["profit_factor"] if m["profit_factor"] is not None else 3.0
    return (0.5 * max(-3.0, min(m["sharpe"], 3.0)) + math.log(max(pf, 0.05))
            - max(0.0, abs(m["max_drawdown_pct"]) - GATE["max_dd_pct"]) / 10)


def bt(strategy: str, symbol: str, df: pd.DataFrame, meta: dict, params: dict, stress: float = 1.0):
    res, _, _ = runner.execute(strategy, runner.instrument(symbol), df, meta, params, cost_stress=stress)
    return res, compute_metrics(res)


def slim(m: dict) -> dict:
    keep = ("trades", "net_profit", "return_pct", "win_rate", "profit_factor", "max_drawdown_pct", "sharpe", "sortino",
            "expectancy")
    return {k: m[k] for k in keep}


# ---------------- optimisation ----------------

def optimise(strategy: str, symbol: str, df: pd.DataFrame, meta: dict, trials: int, job: Job | None = None,
             seed: int = 7, base: dict | None = None) -> tuple[dict, float, list[dict]]:
    space = SPACES[strategy]
    if trials <= 0:  # validate as-is: no search
        _, m = bt(strategy, symbol, df, meta, {**(base or {})})
        return {}, score(m), []
    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    history: list[dict] = []

    def objective(trial):
        if job and job.cancelled:
            raise optuna.TrialPruned()
        p = suggest(trial, space)
        trial.set_user_attr("params", p)
        _, m = bt(strategy, symbol, df, meta, {**(base or {}), **p})
        s = score(m)
        history.append({"trial": trial.number, "score": round(s, 4), **slim(m)})
        if job:
            job.step()
        return s

    study.optimize(objective, n_trials=trials, catch=(ValueError,))
    best = study.best_trial
    return best.user_attrs["params"], best.value, history


# ---------------- validation pieces ----------------

def walk_forward(strategy: str, symbol: str, ins: pd.DataFrame, meta: dict, train_months: int, test_months: int,
                 trials: int, job: Job | None = None, base: dict | None = None) -> dict:
    """Rolling: optimise on `train_months`, test the winner on the next `test_months`, roll by `test_months`."""
    rows, start, end = [], ins.index[0], ins.index[-1]
    while True:
        tr_end = start + pd.DateOffset(months=train_months)
        te_end = tr_end + pd.DateOffset(months=test_months)
        if te_end > end + pd.Timedelta(days=7):
            break
        tr, te = ins[(ins.index >= start) & (ins.index < tr_end)], ins[(ins.index >= tr_end) & (ins.index < te_end)]
        if len(tr) < 500 or len(te) < 50:
            start += pd.DateOffset(months=test_months)
            continue
        best, _, _ = optimise(strategy, symbol, tr, meta, trials, job, seed=len(rows) + 1, base=base)
        best = {**(base or {}), **best}
        _, m_in = bt(strategy, symbol, tr, meta, best)
        _, m_out = bt(strategy, symbol, te, meta, best)
        rows.append({"train": period(tr), "test": period(te), "params": best,
                     "in": slim(m_in), "out": slim(m_out)})
        if job:
            job.step(f"walk-forward window {len(rows)}: test {period(te)[0]} -> {m_out['return_pct']}%")
        start += pd.DateOffset(months=test_months)
    ann_in = np.mean([r["in"]["return_pct"] * 12 / train_months for r in rows]) if rows else 0.0
    ann_out = np.mean([r["out"]["return_pct"] * 12 / test_months for r in rows]) if rows else 0.0
    wfe = float(ann_out / ann_in) if ann_in > 0 else 0.0
    oos_trades = sum(r["out"]["trades"] for r in rows)
    return {"windows": rows, "annual_in_pct": round(float(ann_in), 2), "annual_out_pct": round(float(ann_out), 2),
            "efficiency": round(wfe, 3), "oos_trades": oos_trades,
            "oos_profitable_windows": sum(r["out"]["net_profit"] > 0 for r in rows)}


def monte_carlo(res, risk_pct: float = 0.5, runs: int = 2000, seed: int = 11) -> dict:
    """Reshuffle/bootstrap the trades (in R) and randomise costs (+0..50% spread & slippage per trade)."""
    t = res.trades
    if len(t) < 10:
        return {"runs": 0, "note": "fewer than 10 trades"}
    rng = np.random.default_rng(seed)
    risk = np.array([x.risk_money or np.nan for x in t])
    r = np.array([x.pnl for x in t]) / risk
    cost_r = np.array([(x.spread_cost + x.slippage_cost) for x in t]) / risk
    ok = ~np.isnan(r)
    r, cost_r = r[ok], cost_r[ok]
    n = len(r)
    idx = rng.integers(0, n, size=(runs, n))
    rr = r[idx] - cost_r[idx] * rng.uniform(0, 0.5, size=(runs, n))
    growth = 1 + rr * risk_pct / 100
    eq = np.cumprod(growth, axis=1)
    peak = np.maximum.accumulate(np.concatenate([np.ones((runs, 1)), eq], axis=1), axis=1)[:, 1:]
    dd = (eq / peak - 1).min(axis=1) * 100
    final = (eq[:, -1] - 1) * 100
    q = lambda a, p: round(float(np.percentile(a, p)), 2)  # noqa: E731
    return {"runs": runs, "trades": n, "profit_probability": round(float((final > 0).mean()), 3),
            "return_pct": {"p5": q(final, 5), "p50": q(final, 50), "p95": q(final, 95)},
            "max_dd_pct": {"p50": q(dd, 50), "p95": q(dd, 5)}}  # 95th-percentile WORST drawdown


def sensitivity(strategy: str, symbol: str, df: pd.DataFrame, meta: dict, params: dict, job: Job | None = None,
                base: dict | None = None) -> dict:
    rows = []
    for label, p in neighbours(params, SPACES[strategy]):
        _, m = bt(strategy, symbol, df, meta, {**(base or {}), **p})
        rows.append({"change": label, **slim(m)})
        if job:
            job.step()
    prof = [r for r in rows if r["net_profit"] > 0]
    return {"neighbours": rows, "profitable_share": round(len(prof) / len(rows), 3) if rows else None,
            "worst_pf": min((r["profit_factor"] or 0 for r in rows), default=None)}


def cross_pair(strategy: str, symbol: str, timeframe: str, params: dict, job: Job | None = None) -> list[dict]:
    out = []
    for other in SYMBOLS:
        try:
            sp = load_split(other, timeframe)
        except FileNotFoundError:
            continue
        _, m = bt(strategy, other, sp["insample"], sp["meta"], params)
        out.append({"symbol": other, "is_target": other == symbol, **slim(m)})
        if job:
            job.step()
    return out


# ---------------- gate 1 ----------------

def gate1(report: dict) -> list[dict]:
    """Doc 10.6 checklist. status: pass | fail | pending (hold-out not run yet)."""
    ins, wf, mc, sens = report["insample"], report.get("walk_forward") or {}, report.get("monte_carlo") or {}, report.get("sensitivity") or {}
    stress, pairs, hold = report.get("cost_stress") or {}, report.get("cross_pair") or [], report.get("holdout")
    G = GATE

    def row(name, ok, value, need):
        return {"criterion": name, "status": "pass" if ok else "fail", "value": value, "required": need}

    rows = [
        row("Trades in the sample", ins["trades"] >= G["min_trades"], ins["trades"], f">= {G['min_trades']}"),
        row("Profit factor (net of costs)", (ins["profit_factor"] or 0) >= G["min_pf"], ins["profit_factor"], f">= {G['min_pf']}"),
        row("Max drawdown", abs(ins["max_drawdown_pct"]) <= G["max_dd_pct"], f"{ins['max_drawdown_pct']}%", f"<= {G['max_dd_pct']}%"),
        row("Sharpe / Sortino", ins["sharpe"] >= G["min_sharpe"] or ins["sortino"] >= G["min_sortino"],
            f"{ins['sharpe']} / {ins['sortino']}", f"Sharpe >= {G['min_sharpe']} or Sortino >= {G['min_sortino']}"),
        row("Walk-forward efficiency", wf.get("efficiency", 0) >= G["min_wfe"], wf.get("efficiency"), f">= {G['min_wfe']:.0%}")
        if wf.get("windows") else {"criterion": "Walk-forward efficiency", "status": "fail", "value": "not run", "required": f">= {G['min_wfe']:.0%}"},
        row("Parameter sensitivity", (sens.get("profitable_share") or 0) >= G["min_neighbour_share"],
            sens.get("profitable_share"), f">= {G['min_neighbour_share']:.0%} of neighbours profitable"),
        row("Monte Carlo", mc.get("runs", 0) > 0 and abs(mc["max_dd_pct"]["p95"]) <= G["max_dd_pct"]
            and mc["profit_probability"] >= G["mc_min_profit_prob"],
            f"p95 DD {mc.get('max_dd_pct', {}).get('p95')}%, P(profit) {mc.get('profit_probability')}",
            f"p95 DD <= {G['max_dd_pct']}%, P(profit) >= {G['mc_min_profit_prob']}"),
        row("Cost stress (+50%)", stress.get("net_profit", -1) > 0, stress.get("net_profit"), "still profitable"),
        row("Cross-pair", sum(p["net_profit"] > 0 for p in pairs) >= G["min_profitable_pairs"],
            f"{sum(p['net_profit'] > 0 for p in pairs)} of {len(pairs)} pairs profitable", f">= {G['min_profitable_pairs']} pairs"),
    ]
    if hold is None:
        rows.append({"criterion": "Hold-out (run once)", "status": "pending", "value": "not run yet",
                     "required": f"positive, >= {G['min_holdout_trades']} trades"})
    else:
        rows.append(row("Hold-out (run once)", hold["net_profit"] > 0 and hold["trades"] >= G["min_holdout_trades"],
                        f"{hold['net_profit']} over {hold['trades']} trades", f"positive, >= {G['min_holdout_trades']} trades"))
    return rows


def gate_verdict(rows: list[dict]) -> str:
    if any(r["status"] == "fail" for r in rows):
        return "fail"
    return "pending" if any(r["status"] == "pending" for r in rows) else "pass"


# ---------------- full run ----------------

def run_pipeline(strategy: str, symbol: str, timeframe: str, trials: int = 60, walk_forward_on: bool = True,
                 wf_train_months: int = 12, wf_test_months: int = 3, wf_trials: int = 15,
                 job: Job | None = None, base: dict | None = None) -> dict:
    """`base` = fixed parameters (a rule-builder spec, or settings to validate as-is with trials=0)."""
    base = base or {}
    if trials <= 0:
        wf_trials = 0
    job = job or Job()
    sp = load_split(symbol, timeframe)
    meta = sp["meta"]
    n_neigh = 2 * sum(v[0] != "cat" for v in SPACES[strategy].values())
    months = (sp["insample"].index[-1] - sp["insample"].index[0]).days / 30.4
    wf_windows = max(0, int((months - wf_train_months) // wf_test_months))
    job.total += trials + (wf_windows * (wf_trials + 1) if walk_forward_on else 0) + n_neigh + len(SYMBOLS) + 4

    job.stage = "optimising on training data"
    job.log.append(f"train {period(sp['train'])}, validation {period(sp['valid'])}, hold-out {period(sp['holdout'])}")
    tuned, best_score, history = optimise(strategy, symbol, sp["train"], meta, trials, job, base=base)
    best = {**base, **tuned}
    job.log.append(f"best training score {best_score:.3f}: {tuned or 'settings as given'}")

    job.stage = "validating"
    _, m_train = bt(strategy, symbol, sp["train"], meta, best)
    _, m_valid = bt(strategy, symbol, sp["valid"], meta, best)
    res_ins, m_ins = bt(strategy, symbol, sp["insample"], meta, best)
    _, m_default = bt(strategy, symbol, sp["insample"], meta, {})
    job.step("in-sample backtests done")

    job.stage = "walk-forward"
    wf = walk_forward(strategy, symbol, sp["insample"], meta, wf_train_months, wf_test_months, wf_trials, job,
                      base=base) if walk_forward_on else None

    job.stage = "Monte Carlo, sensitivity, cost stress, cross-pair"
    mc = monte_carlo(res_ins)
    sens = sensitivity(strategy, symbol, sp["insample"], meta, {**_space_defaults(strategy, best), **tuned}, job,
                       base={k: v for k, v in best.items() if k not in tuned})
    _, m_stress = bt(strategy, symbol, sp["insample"], meta, best, stress=1.5)
    job.step("cost stress done")
    pairs = cross_pair(strategy, symbol, timeframe, best, job)

    report = {
        "strategy": strategy, "symbol": symbol, "timeframe": timeframe, "params": best, "tuned": tuned,
        "split": {"train": period(sp["train"]), "validation": period(sp["valid"]), "holdout": period(sp["holdout"])},
        "data_version": meta["data_version"], "trials": trials, "best_score": round(best_score, 4),
        "history": history, "train": slim(m_train), "validation": slim(m_valid), "insample": slim(m_ins),
        "defaults_insample": slim(m_default), "walk_forward": wf, "monte_carlo": mc, "sensitivity": sens,
        "cost_stress": slim(m_stress), "cross_pair": pairs, "holdout": None,
        "multiple_testing_note": f"{trials} parameter sets were tried on training data"
        + (f" plus {wf_trials} per walk-forward window" if walk_forward_on else "")
        + "; the more combinations tried, the more likely the best one is lucky. Trust validation, walk-forward and hold-out, not training.",
    }
    report["gate1"] = gate1(report)
    report["verdict"] = gate_verdict(report["gate1"])
    job.stage = "done"
    return report


def _space_defaults(strategy: str, params: dict) -> dict:
    """Values for every numeric space parameter: from `params` when given, else the strategy's own default,
    so sensitivity can always perturb them (also when validating as-is)."""
    from app.backtest.runner import STRATEGIES
    from app.strategies.structure_base import DEFAULTS
    cls = STRATEGIES[strategy]
    own = {**DEFAULTS, **getattr(cls, "defaults", {})}
    known = {"rr": 2.0, "atr_mult": 1.5, "fast": 20, "slow": 50, "adx_min": 20, "fan_bars": 3, "trend_ema": 200,
             "sl_buffer_atr": 0.2, "threshold": 6, "buffer_atr": 0.2, "min_rr": 2.0, "window": 30, "max_wait": 200,
             "ote": 0.705, "target_ext": 0.27, "sweep_lookback": 40}
    rule = params.get("spec") if strategy == "RULE" else None
    if isinstance(rule, dict):  # a rule's own values live inside its spec
        tp = (rule.get("exit") or {}).get("take_profit") or {}
        st = rule.get("structure") or {}
        own = {**own, "threshold": rule.get("threshold", 6), "buffer_atr": (rule.get("exit") or {}).get("buffer_atr", 0.2),
               "rr": tp.get("rr", 2.0), "min_rr": tp.get("min_rr", 2.0), **{k: st[k] for k in st}}
    out = {}
    for k, spec in SPACES[strategy].items():
        if spec[0] != "cat":
            out[k] = params.get(k, own.get(k, known.get(k, spec[1])))
    return out


def run_holdout(strategy: str, symbol: str, timeframe: str, params: dict) -> dict:
    sp = load_split(symbol, timeframe)
    _, m = bt(strategy, symbol, sp["holdout"], sp["meta"], params)
    return {"period": period(sp["holdout"]), **slim(m)}
