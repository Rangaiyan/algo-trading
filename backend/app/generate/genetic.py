"""Strategy generator (doc 9.3, Phase 4): search block combinations, then validate the survivors.

A candidate ("genome") is a Rule Builder spec (app/strategies/rules.py): which blocks are on, their options,
confluence weights + threshold, entry, exit and structure settings. Candidates are scored on the TRAINING split
only, with the same composite score as the optimiser. The best few DISTINCT candidates then go through the full
Phase 3 validation (validation split, walk-forward, Monte Carlo, sensitivity, cost stress, cross-pair, Gate 1),
plus a multiple-testing check: the more candidates tried, the better the best one looks by luck alone.
"""
from __future__ import annotations

import copy
import json
import math
import random

from app.optimize import pipeline as OP
from app.strategies.rules import validate_spec

STRUCT = {"swing_n": [2, 3, 4], "displacement_k": [1.25, 1.5, 2.0], "fvg_min_atr": [0.2, 0.3, 0.5]}
OPTIONAL = ["liquidity_sweep", "htf_bias", "premium_discount", "ema_trend", "candle_confirm", "session"]
LEVEL_SETS = [["prev_day_hl"], ["asia_hl"], ["equal_hl"], ["swing_hl"], ["prev_day_hl", "asia_hl"],
              ["prev_day_hl", "asia_hl", "equal_hl"], ["prev_day_hl", "prev_week_hl"]]
SESSION_SETS = [["london_kz"], ["ny_am_kz"], ["london_kz", "ny_am_kz"], ["silver_bullet_am", "silver_bullet_pm"]]
PATTERN_SETS = [["engulfing"], ["pin_bar"], ["engulfing", "pin_bar"], ["engulfing", "pin_bar", "star"]]
EMAS = [(20, 50), (50, 200), (21, 100)]


def _block(name: str, rng: random.Random) -> dict:
    w = rng.choice([1, 2, 3])
    if name == "liquidity_sweep":
        return {"block": name, "levels": rng.choice(LEVEL_SETS), "within": rng.choice([10, 20, 30, 50]), "weight": w}
    if name == "ema_trend":
        f, s = rng.choice(EMAS)
        return {"block": name, "fast": f, "slow": s, "weight": w}
    if name == "candle_confirm":
        return {"block": name, "patterns": rng.choice(PATTERN_SETS), "weight": w}
    if name == "session":
        return {"block": name, "sessions": rng.choice(SESSION_SETS), "weight": w}
    return {"block": name, "weight": w}


def _fix(spec: dict, rng: random.Random) -> dict:
    """Keep a spec valid and sensible: trigger first, threshold within reach, stop type usable."""
    blocks = [b for b in spec["setup"] if b["block"] != "structure_break"]
    trig = next((b for b in spec["setup"] if b["block"] == "structure_break"), None) or \
        {"block": "structure_break", "kind": "any", "displacement": True, "weight": 2}
    seen, uniq = set(), []
    for b in blocks:
        if b["block"] not in seen:
            seen.add(b["block"])
            uniq.append(b)
    spec["setup"] = [trig, *uniq]
    total = sum(b.get("weight", 1) for b in spec["setup"])
    if spec["mode"] == "score":
        spec["threshold"] = max(1, min(int(spec.get("threshold") or total), total))
    if spec["exit"]["stop"] == "sweep" and "liquidity_sweep" not in seen:
        spec["exit"]["stop"] = rng.choice(["zone", "atr"])
    if spec["entry"]["type"] == "market" and spec["exit"]["stop"] == "zone":
        spec["exit"]["stop"] = "atr"
    return spec


def random_spec(rng: random.Random) -> dict:
    blocks = rng.sample(OPTIONAL, rng.randint(1, 4))
    mode = rng.choice(["all", "score"])
    setup = [{"block": "structure_break", "kind": rng.choice(["any", "BOS", "CHoCH"]),
              "displacement": rng.random() < 0.6, "weight": rng.choice([1, 2, 3])}] + [_block(b, rng) for b in blocks]
    total = sum(b["weight"] for b in setup)
    tp_type = rng.choice(["rr", "next_liquidity"])
    spec = {
        "structure": {k: rng.choice(v) for k, v in STRUCT.items()},
        "filters": {"sessions": rng.choice([[], *SESSION_SETS])} if rng.random() < 0.4 else {},
        "mode": mode, "threshold": rng.randint(max(1, math.ceil(total * 0.5)), total) if mode == "score" else None,
        "setup": setup,
        "entry": {"type": "zone" if rng.random() < 0.75 else "market",
                  "zone": rng.choice([["ob"], ["fvg"], ["ob", "fvg"], ["fvg", "ob"]]),
                  "at": rng.choice(["edge", "mid"]), "expires_bars": rng.choice([10, 20, 40])},
        "exit": {"stop": rng.choice(["sweep", "zone", "atr"]), "buffer_atr": rng.choice([0.1, 0.2, 0.3, 0.5]),
                 "atr_mult": rng.choice([1.0, 1.5, 2.0]),
                 "take_profit": {"type": tp_type, "rr": rng.choice([1.5, 2.0, 2.5, 3.0]), "min_rr": rng.choice([1.5, 2.0, 2.5])}},
    }
    if mode != "score":
        spec.pop("threshold")
    return _fix(spec, rng)


def mutate(spec: dict, rng: random.Random, n: int = 2) -> dict:
    s = copy.deepcopy(spec)
    for _ in range(n):
        what = rng.choice(["toggle", "toggle", "option", "weight", "threshold", "structure", "entry", "exit", "mode"])
        on = {b["block"] for b in s["setup"]}
        if what == "toggle":
            name = rng.choice(OPTIONAL)
            if name in on and len(s["setup"]) > 2:
                s["setup"] = [b for b in s["setup"] if b["block"] != name]
            elif name not in on:
                s["setup"].append(_block(name, rng))
        elif what == "option":
            k = rng.randrange(len(s["setup"]))
            b = s["setup"][k]
            if b["block"] == "structure_break":
                b["kind"], b["displacement"] = rng.choice(["any", "BOS", "CHoCH"]), rng.random() < 0.6
            else:
                s["setup"][k] = {**_block(b["block"], rng), "weight": b.get("weight", 1)}
        elif what == "weight":
            rng.choice(s["setup"])["weight"] = rng.choice([1, 2, 3])
        elif what == "threshold" and s["mode"] == "score":
            s["threshold"] = s.get("threshold", 3) + rng.choice([-1, 1])
        elif what == "structure":
            k = rng.choice(list(STRUCT))
            s["structure"][k] = rng.choice(STRUCT[k])
        elif what == "entry":
            fresh = random_spec(rng)["entry"]
            k = rng.choice(["type", "zone", "at", "expires_bars"])
            s["entry"][k] = fresh[k]
        elif what == "exit":
            fresh = random_spec(rng)["exit"]
            key = rng.choice(["stop", "buffer_atr", "take_profit"])
            s["exit"][key] = fresh[key]
        elif what == "mode":
            s["mode"] = "all" if s["mode"] == "score" else "score"
            if s["mode"] == "score":
                s["threshold"] = math.ceil(sum(b.get("weight", 1) for b in s["setup"]) * 0.6)
            else:
                s.pop("threshold", None)
    return _fix(s, rng)


def crossover(a: dict, b: dict, rng: random.Random) -> dict:
    """Child takes each block from either parent (or neither), and each section (entry/exit/structure/mode) from one."""
    child = copy.deepcopy(rng.choice([a, b]))
    pool = {x["block"]: x for x in a["setup"] + b["setup"]}
    trig = rng.choice([x for x in (a["setup"][0], b["setup"][0])])
    picked = [copy.deepcopy(v) for k, v in pool.items() if k != "structure_break" and rng.random() < 0.5]
    child["setup"] = [copy.deepcopy(trig), *(picked or [copy.deepcopy(rng.choice(list(pool.values())))])]
    for sec in ("entry", "exit", "structure", "filters"):
        child[sec] = copy.deepcopy(rng.choice([a, b]).get(sec, {}))
    return _fix(child, rng)


def key(spec: dict) -> str:
    return json.dumps({k: v for k, v in spec.items() if k != "name"}, sort_keys=True)


def signature(spec: dict) -> str:
    """Coarse shape: which blocks + entry/exit types. Survivors must differ in shape, not just in numbers."""
    blocks = sorted(b["block"] for b in spec["setup"])
    return f"{'+'.join(blocks)}|{spec['entry']['type']}|{spec['exit']['stop']}|{spec['exit']['take_profit']['type']}"


def describe(spec: dict) -> str:
    trig = spec["setup"][0]
    parts = [f"{trig.get('kind', 'any')}{' + disp' if trig.get('displacement') else ''}"]
    for b in spec["setup"][1:]:
        n = b["block"]
        if n == "liquidity_sweep":
            parts.append(f"sweep({'/'.join(x.replace('_hl', '') for x in b.get('levels', []))})")
        elif n == "ema_trend":
            parts.append(f"EMA{b.get('fast', 50)}/{b.get('slow', 200)}")
        elif n == "session":
            parts.append(f"in {'/'.join(b.get('sessions', []))}")
        else:
            parts.append({"candle_confirm": "candle", "htf_bias": "H4 bias", "premium_discount": "P/D"}.get(n, n))
    mode = f"score>={spec['threshold']}" if spec["mode"] == "score" else "all"
    en, ex = spec["entry"], spec["exit"]
    tp = ex["take_profit"]
    entry = f"{'/'.join(en['zone'])} {en['at']}" if en["type"] == "zone" else "market"
    target = f"{tp['rr']}R" if tp["type"] == "rr" else f"next liq >= {tp['min_rr']}R"
    return f"{' + '.join(parts)} [{mode}] | {entry} | stop {ex['stop']} | {target}"


class _Stop(Exception):
    """Raised inside the search when the job is cancelled."""


def luck_sharpe(n_candidates: int, years: float) -> float:
    """Expected best annualised Sharpe among n skill-less strategies over `years` (~ sqrt(2 ln n) / sqrt(years))."""
    if n_candidates < 2 or years <= 0:
        return 0.0
    return round(math.sqrt(2 * math.log(n_candidates)) / math.sqrt(years), 3)


def generate(symbol: str, timeframe: str, population: int = 24, generations: int = 6, survivors: int = 3,
             method: str = "genetic", seed: int = 7, job: OP.Job | None = None) -> dict:
    job = job or OP.Job()
    rng = random.Random(seed)
    sp = OP.load_split(symbol, timeframe)
    train, meta = sp["train"], sp["meta"]
    evals = population * generations
    job.total = evals  # validation adds its own steps later
    seen: dict[str, dict] = {}

    def fitness(spec: dict) -> dict:
        if job.cancelled:
            raise _Stop
        k = key(spec)
        if k not in seen:
            assert not validate_spec(spec), validate_spec(spec)
            _, m = OP.bt("RULE", symbol, train, meta, {"spec": spec})
            seen[k] = {"spec": spec, "score": round(OP.score(m), 4), "train": OP.slim(m), "describe": describe(spec)}
            job.step()
        return seen[k]

    curve: list[dict] = []

    def _search():
        if method == "random":
            job.stage = "random search on training data"
            for g in range(generations):
                for _ in range(population):
                    fitness(random_spec(rng))
                best = max(seen.values(), key=lambda c: c["score"])
                curve.append({"generation": g + 1, "best": best["score"], "evaluated": len(seen)})
        else:
            job.stage = "genetic search on training data"
            pop = [random_spec(rng) for _ in range(population)]
            for g in range(generations):
                scored = sorted((fitness(s) for s in pop), key=lambda c: c["score"], reverse=True)
                curve.append({"generation": g + 1, "best": scored[0]["score"],
                              "median": scored[len(scored) // 2]["score"], "evaluated": len(seen)})
                job.log.append(f"generation {g + 1}: best {scored[0]['score']:.3f} ({scored[0]['train']['trades']} trades) {scored[0]['describe']}")
                if g == generations - 1:
                    break
                elite = [c["spec"] for c in scored[:2]]

                def pick():
                    return max(rng.sample(scored, min(3, len(scored))), key=lambda c: c["score"])["spec"]

                nxt = list(elite)
                while len(nxt) < population:
                    child = crossover(pick(), pick(), rng) if rng.random() < 0.7 else copy.deepcopy(pick())
                    nxt.append(mutate(child, rng, n=rng.choice([1, 2, 3])))
                pop = nxt

    try:
        _search()
    except _Stop:
        job.log.append("cancelled: keeping the candidates scored so far, skipping validation")

    ranked = sorted(seen.values(), key=lambda c: c["score"], reverse=True)
    train_years = (train.index[-1] - train.index[0]).days / 365.25
    luck = luck_sharpe(len(seen), train_years)

    job.stage = "validating survivors"
    job.total = job.done  # duplicates were skipped; each validation run adds its own steps
    chosen, shapes = [], set()
    for c in ranked:
        if len(chosen) >= survivors:
            break
        if c["train"]["trades"] < OP.MIN_TRAIN_TRADES or signature(c["spec"]) in shapes:
            continue
        shapes.add(signature(c["spec"]))
        chosen.append(c)

    results = []
    for n, c in enumerate([] if job.cancelled else chosen, 1):
        spec = dict(c["spec"], name=f"GEN {symbol} {timeframe} #{n}: {c['describe']}"[:120])
        job.log.append(f"validating #{n}: {c['describe']}")
        rep = OP.run_pipeline("RULE", symbol, timeframe, trials=0, walk_forward_on=True, job=job, base={"spec": spec})
        beats = rep["train"]["sharpe"] > luck
        rep["gate1"].insert(0, {"criterion": "Beats the multiple-testing luck benchmark", "status": "pass" if beats else "fail",
                                "value": f"train Sharpe {rep['train']['sharpe']}",
                                "required": f"> {luck} (best of {len(seen)} random strategies by luck)"})
        rep["verdict"] = OP.gate_verdict(rep["gate1"])
        rep["multiple_testing_note"] = (f"{len(seen)} distinct candidates were scored on training data; by luck alone the best of that many "
                                        f"would reach a training Sharpe of about {luck}.")
        results.append({"describe": c["describe"], "score": c["score"], "spec": spec, "report": rep})

    job.stage = "done"
    return {
        "symbol": symbol, "timeframe": timeframe, "method": method, "population": population, "generations": generations,
        "evaluated": len(seen), "train_period": OP.period(train), "luck_sharpe": luck, "curve": curve,
        "leaderboard": [{k: c[k] for k in ("describe", "score", "train")} | {"spec": c["spec"]} for c in ranked[:25]],
        "survivors": results,
        "passed": sum(r["report"]["verdict"] in ("pass", "pending") for r in results),
    }
