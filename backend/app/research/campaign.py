"""Backtest stage (doc 10.3): one structured campaign over strategies x pairs x timeframes.

  1. Baselines   - every strategy with its default settings on the in-sample data (hold-out never touched)
  2. Shortlist   - the strongest distinct strategy/pair/timeframe combinations (enough trades, best score)
  3. Validation  - each shortlisted combination is optimised on TRAINING data and validated (Gate 1 pipeline)
  4. Generator   - optional rule-generator runs per pair/timeframe, survivors validated the same way
  5. Report      - baseline heatmap, ranked candidates with Gate 1 verdicts; Gate-1-passing candidates (hold-out
                   still pending) are saved to the Strategy Library so the hold-out can be run there, once.

Results only count once Gate 0 (engine vs MT5 Strategy Tester) has passed; the report states its status.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.backtest.runner import STRATEGIES
from app.data.mt5_history import SYMBOLS
from app.generate import genetic
from app.library import store
from app.optimize import pipeline as OP

ROOT = Path("runtime") / "campaigns"
GATE0_FILE = Path("runtime") / "gate0_last.json"
DEFAULT_STRATEGIES = [s for s in STRATEGIES if s != "RULE"]
MIN_BASELINE_TRADES = 60


def gate0_status() -> dict:
    if not GATE0_FILE.exists():
        return {"status": "not run", "note": "Run RinzGate0 in the MT5 Strategy Tester and compare it on the Gate 0 Check page."}
    g = json.loads(GATE0_FILE.read_text())
    return {"status": g.get("verdict"), "at": g.get("at"), "symbol": g.get("symbol"), "timeframe": g.get("timeframe"),
            "match_rate": (g.get("summary") or {}).get("match_rate")}


def run_campaign(symbols: list[str] | None = None, timeframes: list[str] | None = None, strategies: list[str] | None = None,
                 shortlist: int = 6, trials: int = 40, wf_trials: int = 10, generator: bool = False,
                 gen_population: int = 16, gen_generations: int = 4, save_passing: bool = True,
                 job: OP.Job | None = None) -> dict:
    job = job or OP.Job()
    symbols, timeframes = symbols or SYMBOLS, timeframes or ["H1", "H4"]
    strategies = [s for s in (strategies or DEFAULT_STRATEGIES) if s in STRATEGIES and s != "RULE"]
    cid = f"{datetime.now(UTC):%Y%m%d-%H%M}-{uuid.uuid4().hex[:4]}"
    started = datetime.now(UTC).isoformat(timespec="seconds")
    job.total = len(symbols) * len(timeframes) * len(strategies)

    # ---- 1. baselines (defaults, in-sample) ----
    job.stage = "baselines (default settings, in-sample)"
    baselines, splits = [], {}
    for sym in symbols:
        for tf in timeframes:
            try:
                splits[(sym, tf)] = OP.load_split(sym, tf)
            except FileNotFoundError:
                job.log.append(f"skipped {sym} {tf}: no downloaded data")
                job.done += len(strategies)
                continue
            sp = splits[(sym, tf)]
            for st in strategies:
                if job.cancelled:
                    break
                try:
                    _, m = OP.bt(st, sym, sp["insample"], sp["meta"], {})
                    baselines.append({"strategy": st, "symbol": sym, "timeframe": tf, "score": round(OP.score(m, MIN_BASELINE_TRADES), 4),
                                      **OP.slim(m)})
                except Exception as e:  # noqa: BLE001 - one bad combination must not stop the campaign
                    baselines.append({"strategy": st, "symbol": sym, "timeframe": tf, "error": f"{type(e).__name__}: {e}"})
                job.step()
            job.log.append(f"baselines done: {sym} {tf}")

    # ---- 2. shortlist: best per strategy first (diversity), then by score ----
    ok = sorted([b for b in baselines if "error" not in b and b["trades"] >= MIN_BASELINE_TRADES], key=lambda b: -b["score"])
    picked, seen_strat = [], set()
    for b in ok:
        if len(picked) >= shortlist:
            break
        if b["strategy"] not in seen_strat:
            picked.append(b)
            seen_strat.add(b["strategy"])
    for b in ok:
        if len(picked) >= shortlist:
            break
        if b not in picked:
            picked.append(b)

    # ---- 3. optimise + validate each shortlisted combination ----
    job.stage = "optimising and validating the shortlist"
    candidates = []
    for n, b in enumerate(picked, 1):
        if job.cancelled:
            break
        job.log.append(f"[{n}/{len(picked)}] optimise + validate {b['strategy']} {b['symbol']} {b['timeframe']}")
        try:
            rep = OP.run_pipeline(b["strategy"], b["symbol"], b["timeframe"], trials=trials, wf_trials=wf_trials, job=job)
            candidates.append({"source": "optimiser", "strategy": b["strategy"], "symbol": b["symbol"], "timeframe": b["timeframe"],
                               "baseline": {k: b[k] for k in ("trades", "profit_factor", "return_pct", "score")}, "report": rep})
        except Exception as e:  # noqa: BLE001
            job.log.append(f"   failed: {type(e).__name__}: {e}")

    # ---- 4. optional generator runs ----
    if generator and not job.cancelled:
        job.stage = "strategy generator"
        for sym in symbols:
            for tf in timeframes:
                if job.cancelled or (sym, tf) not in splits:
                    continue
                job.log.append(f"generator {sym} {tf}")
                try:
                    g = genetic.generate(sym, tf, population=gen_population, generations=gen_generations, survivors=1, job=job)
                    for s in g["survivors"]:
                        candidates.append({"source": "generator", "strategy": "RULE", "symbol": sym, "timeframe": tf,
                                           "describe": s["describe"], "report": s["report"]})
                except Exception as e:  # noqa: BLE001
                    job.log.append(f"   generator failed: {type(e).__name__}: {e}")

    # ---- 5. rank, save passing ones, report ----
    order = {"pass": 0, "pending": 1, "fail": 2}

    def rank(c):
        r = c["report"]
        fails = sum(g["status"] == "fail" for g in r["gate1"])
        return (order.get(r["verdict"], 3), fails, -(r["validation"]["profit_factor"] or 0))

    candidates.sort(key=rank)
    saved = []
    if save_passing:
        for c in candidates:
            if c["report"]["verdict"] in ("pass", "pending"):
                params = c["report"]["params"]
                e = store.create(f"Campaign {cid}: {c['strategy']} {c['symbol']} {c['timeframe']}", c["strategy"], c["symbol"],
                                 c["timeframe"], params, report=c["report"], spec=params.get("spec"))
                c["library_id"] = e["id"]
                saved.append(e["id"])

    slim_candidates = [{**{k: v for k, v in c.items() if k != "report"},
                        "verdict": c["report"]["verdict"], "params": c["report"]["tuned"] or c["report"]["params"],
                        "gate1": c["report"]["gate1"], "train": c["report"]["train"], "validation": c["report"]["validation"],
                        "insample": c["report"]["insample"], "walk_forward_efficiency": (c["report"]["walk_forward"] or {}).get("efficiency"),
                        "cross_pair": [{"symbol": p["symbol"], "profit_factor": p["profit_factor"]} for p in c["report"]["cross_pair"]]}
                       for c in candidates]
    result = {
        "id": cid, "started_at": started, "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "settings": {"symbols": symbols, "timeframes": timeframes, "strategies": strategies, "shortlist": shortlist,
                     "trials": trials, "wf_trials": wf_trials, "generator": generator},
        "gate0": gate0_status(), "baselines": baselines, "shortlist": picked, "candidates": slim_candidates,
        "passed": sum(c["verdict"] in ("pass", "pending") for c in slim_candidates), "saved_to_library": saved,
        "cancelled": job.cancelled,
        "conclusion": ("At least one candidate passed every Gate 1 check except the hold-out: run its hold-out test once in the "
                       "Strategy Library." if saved else
                       "No candidate passed Gate 1. Per the plan, the answer is to keep researching (new ideas, other "
                       "timeframes, the generator), not to lower the bar."),
    }
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / f"{cid}.json").write_text(json.dumps(result, indent=1, default=str))
    job.stage = "done"
    return result


def list_campaigns() -> list[dict]:
    if not ROOT.exists():
        return []
    out = []
    for p in sorted(ROOT.glob("*.json"), reverse=True):
        r = json.loads(p.read_text())
        out.append({k: r.get(k) for k in ("id", "started_at", "finished_at", "settings", "passed", "saved_to_library", "gate0", "cancelled")}
                   | {"candidates": len(r.get("candidates") or []), "baselines": len(r.get("baselines") or [])})
    return out


def get_campaign(cid: str) -> dict:
    p = ROOT / f"{cid}.json"
    if not p.is_file() or p.parent.resolve() != ROOT.resolve():
        raise KeyError(cid)
    return json.loads(p.read_text())
