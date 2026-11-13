"""Phase 3 API: optimisation + validation jobs, strategy library / lifecycle, rule-builder helpers."""
from __future__ import annotations

import threading
import traceback
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.backtest.runner import STRATEGIES
from app.generate import genetic
from app.research import campaign
from app.library import store
from app.optimize import basket, pipeline
from app.optimize.spaces import SPACES
from app.patterns.candles import BULLISH
from app.strategies import rules

router = APIRouter(tags=["phase3"])

_jobs: dict[str, dict] = {}
_lock = threading.Lock()


class OptimizeRequest(BaseModel):
    strategy: str
    symbol: str = "EURUSD"
    symbols: list[str] | None = None             # 2+ pairs = basket: one rule set, shared settings, combined result
    timeframe: str = "H1"
    trials: int = Field(60, ge=0, le=500)       # 0 = validate the given settings as-is
    walk_forward: bool = True
    wf_train_months: int = Field(12, ge=3, le=36)
    wf_test_months: int = Field(3, ge=1, le=12)
    wf_trials: int = Field(15, ge=0, le=100)
    base: dict = {}                              # fixed params, e.g. {"spec": {...}} for RULE


def _launch(kind: str, request: dict, fn) -> str:
    """Run fn(job) in a background thread; one heavy job at a time."""
    with _lock:
        if any(j["status"] == "running" for j in _jobs.values()):
            raise HTTPException(409, "A job is already running (optimiser or generator). Wait for it or cancel it.")
        jid = uuid.uuid4().hex[:10]
        job = pipeline.Job()
        _jobs[jid] = {"id": jid, "kind": kind, "status": "running", "request": request, "job": job, "result": None,
                      "error": None, "started_at": datetime.now(UTC).isoformat(), "finished_at": None}

    def work():
        rec = _jobs[jid]
        try:
            rec["result"] = fn(job)
            rec["status"] = "cancelled" if job.cancelled else "done"
        except FileNotFoundError as e:
            rec["status"], rec["error"] = "error", f"{e}. Download the data on Market Data first."
        except Exception as e:  # noqa: BLE001 - shown in the UI
            rec["status"], rec["error"] = "error", f"{type(e).__name__}: {e}"
            traceback.print_exc()
        finally:
            rec["finished_at"] = datetime.now(UTC).isoformat()

    threading.Thread(target=work, daemon=True).start()
    return jid


@router.get("/optimize/spaces")
def spaces() -> dict:
    return {k: {n: list(v) for n, v in s.items()} for k, s in SPACES.items()} | {"_gate": pipeline.GATE}


@router.post("/optimize")
def start(req: OptimizeRequest) -> dict:
    if req.strategy not in STRATEGIES or req.strategy not in SPACES:
        raise HTTPException(404, f"unknown strategy '{req.strategy}'")
    if req.strategy == "RULE":
        errs = rules.validate_spec(req.base.get("spec") or {})
        if errs:
            raise HTTPException(422, "; ".join(errs))
    pairs = list(dict.fromkeys(req.symbols or []))
    if len(pairs) >= 2:
        jid = _launch("optimize", req.model_dump(), lambda job: basket.run_basket_pipeline(
            req.strategy, pairs, req.timeframe, trials=req.trials, walk_forward_on=req.walk_forward,
            wf_train_months=req.wf_train_months, wf_test_months=req.wf_test_months, wf_trials=req.wf_trials,
            job=job, base=req.base))
        return {"job_id": jid}
    jid = _launch("optimize", req.model_dump(), lambda job: pipeline.run_pipeline(
        req.strategy, pairs[0] if pairs else req.symbol, req.timeframe, trials=req.trials, walk_forward_on=req.walk_forward,
        wf_train_months=req.wf_train_months, wf_test_months=req.wf_test_months, wf_trials=req.wf_trials,
        job=job, base=req.base))
    return {"job_id": jid}


class CampaignRequest(BaseModel):
    symbols: list[str] | None = None
    timeframes: list[str] = ["H1", "H4"]
    strategies: list[str] | None = None
    shortlist: int = Field(6, ge=1, le=20)
    trials: int = Field(40, ge=0, le=300)
    wf_trials: int = Field(10, ge=0, le=60)
    generator: bool = False
    save_passing: bool = True


@router.post("/campaign")
def start_campaign(req: CampaignRequest) -> dict:
    """Backtest stage (doc 10.3): baselines -> shortlist -> optimise + validate -> report."""
    jid = _launch("campaign", req.model_dump(), lambda job: campaign.run_campaign(
        req.symbols, req.timeframes, req.strategies, shortlist=req.shortlist, trials=req.trials, wf_trials=req.wf_trials,
        generator=req.generator, save_passing=req.save_passing, job=job))
    return {"job_id": jid}


@router.get("/campaigns")
def campaigns() -> dict:
    return {"campaigns": campaign.list_campaigns(), "gate0": campaign.gate0_status()}


@router.get("/campaigns/{cid}")
def campaign_detail(cid: str) -> dict:
    try:
        return campaign.get_campaign(cid)
    except KeyError as e:
        raise HTTPException(404, "unknown campaign") from e


class GenerateRequest(BaseModel):
    symbol: str = "EURUSD"
    timeframe: str = "H1"
    method: str = Field("genetic", pattern="^(genetic|random)$")
    population: int = Field(24, ge=4, le=200)
    generations: int = Field(6, ge=1, le=50)
    survivors: int = Field(3, ge=1, le=10)
    seed: int = 7


@router.post("/generate")
def start_generate(req: GenerateRequest) -> dict:
    """Phase 4: search rule-block combinations on training data, then validate the best distinct survivors."""
    jid = _launch("generate", req.model_dump(), lambda job: genetic.generate(
        req.symbol, req.timeframe, population=req.population, generations=req.generations, survivors=req.survivors,
        method=req.method, seed=req.seed, job=job))
    return {"job_id": jid}


def _view(rec: dict, full: bool = True) -> dict:
    j: pipeline.Job = rec["job"]
    return {"id": rec["id"], "kind": rec.get("kind", "optimize"), "status": rec["status"], "request": rec["request"],
            "stage": j.stage, "done": j.done,
            "total": max(j.total, j.done), "log": j.log[-40:], "error": rec["error"], "started_at": rec["started_at"],
            "finished_at": rec["finished_at"], "result": rec["result"] if full else None}


@router.get("/optimize/jobs")
def jobs() -> list[dict]:
    return [_view(r, full=False) for r in sorted(_jobs.values(), key=lambda r: r["started_at"], reverse=True)][:20]


@router.get("/optimize/{jid}")
def status(jid: str) -> dict:
    if jid not in _jobs:
        raise HTTPException(404, "unknown job (jobs are kept in memory until the backend restarts)")
    return _view(_jobs[jid])


@router.post("/optimize/{jid}/cancel")
def cancel(jid: str) -> dict:
    if jid not in _jobs:
        raise HTTPException(404, "unknown job")
    _jobs[jid]["job"].cancelled = True
    return {"cancelled": True}


# ---------------- library ----------------

class SaveRequest(BaseModel):
    job_id: str | None = None
    candidate: int | None = None  # generator jobs: which survivor (0-based)
    name: str = ""
    strategy: str | None = None
    symbol: str | None = None
    timeframe: str | None = None
    params: dict = {}


class PromoteRequest(BaseModel):
    to: str
    note: str = ""


@router.get("/library")
def library() -> list[dict]:
    return store.list_all()


@router.get("/library/{eid}")
def library_entry(eid: str) -> dict:
    try:
        return store.get(eid)
    except KeyError as e:
        raise HTTPException(404, "unknown library entry") from e


@router.post("/library")
def library_save(req: SaveRequest) -> dict:
    if req.job_id:
        rec = _jobs.get(req.job_id)
        if not rec or not rec["result"]:
            raise HTTPException(404, "that job has no finished result")
        r = rec["result"]
        if rec.get("kind") == "generate":
            if req.candidate is None or not 0 <= req.candidate < len(r["survivors"]):
                raise HTTPException(422, "choose a survivor (candidate index)")
            sv = r["survivors"][req.candidate]
            rep = sv["report"]
            return store.create(req.name or sv["spec"].get("name", ""), "RULE", r["symbol"], r["timeframe"], rep["params"],
                                report=rep, spec=sv["spec"])
        return store.create(req.name, r["strategy"], r["symbol"], r["timeframe"], r["params"], report=r,
                            spec=r["params"].get("spec"))
    if not (req.strategy and req.symbol and req.timeframe):
        raise HTTPException(422, "give a job_id, or strategy + symbol + timeframe")
    return store.create(req.name, req.strategy, req.symbol, req.timeframe, req.params, spec=req.params.get("spec"))


@router.post("/library/{eid}/promote")
def library_promote(eid: str, req: PromoteRequest) -> dict:
    try:
        return store.promote(eid, req.to, req.note)
    except KeyError as e:
        raise HTTPException(404, "unknown library entry") from e
    except store.LifecycleError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/library/{eid}/holdout")
def library_holdout(eid: str, confirm_rerun: bool = False) -> dict:
    """Run the untouched hold-out ONCE (doc 10.5). A second run needs confirm_rerun and is flagged."""
    try:
        e = store.get(eid)
    except KeyError as err:
        raise HTTPException(404, "unknown library entry") from err
    if not e.get("report"):
        raise HTTPException(409, "Validate the strategy first (run it through the optimiser).")
    if e.get("holdout_used") and not confirm_rerun:
        raise HTTPException(409, "The hold-out was already used for this strategy. Re-running makes it no longer an "
                                 "independent test; pass confirm_rerun=true if you really want to.")
    if "+" in e["symbol"]:  # basket entry: the hold-out runs on every pair together
        res = basket.run_basket_holdout(e["strategy"], e["symbol"].split("+"), e["timeframe"], e["params"])
    else:
        res = pipeline.run_holdout(e["strategy"], e["symbol"], e["timeframe"], e["params"])
    rep = dict(e["report"], holdout=res)
    rows = pipeline.gate1(rep)
    return store.record_holdout(eid, res, rows, pipeline.gate_verdict(rows))


@router.delete("/library/{eid}")
def library_delete(eid: str) -> dict:
    try:
        store.delete(eid)
    except (KeyError, FileNotFoundError) as e:
        raise HTTPException(404, "unknown library entry") from e
    return {"deleted": eid}


# ---------------- rule builder ----------------

class SpecRequest(BaseModel):
    spec: dict


@router.get("/builder/blocks")
def builder_blocks() -> dict:
    return {"blocks": rules.BLOCKS, "sessions": rules.SESSIONS, "levels": sorted(rules.LEVEL_GROUPS),
            "patterns": sorted(BULLISH), "example": rules.EXAMPLE}


@router.post("/builder/validate")
def builder_validate(req: SpecRequest) -> dict:
    return {"errors": rules.validate_spec(req.spec)}
