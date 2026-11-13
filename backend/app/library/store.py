"""Strategy library and lifecycle (doc 9.4): draft -> backtested -> validated -> paper -> live -> retired.

Each entry is one JSON file in strategy_library/ (kept in git): the strategy, its parameters, every version,
its reports (optimisation + validation + gate, hold-out) and its status history.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = "strategy_library"
STATUSES = ["draft", "backtested", "validated", "paper", "live", "retired"]


class LifecycleError(ValueError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _path(entry_id: str, root: str = ROOT) -> Path:
    if not re.fullmatch(r"[a-z0-9-]{4,80}", entry_id):
        raise KeyError(entry_id)
    return Path(root) / f"{entry_id}.json"


def save(entry: dict, root: str = ROOT) -> dict:
    Path(root).mkdir(parents=True, exist_ok=True)
    _path(entry["id"], root).write_text(json.dumps(entry, indent=1, default=str))
    return entry


def get(entry_id: str, root: str = ROOT) -> dict:
    p = _path(entry_id, root)
    if not p.exists():
        raise KeyError(entry_id)
    return json.loads(p.read_text())


def list_all(root: str = ROOT) -> list[dict]:
    out = []
    for p in sorted(Path(root).glob("*.json")):
        e = json.loads(p.read_text())
        rep = e.get("report") or {}
        out.append({k: e.get(k) for k in ("id", "name", "strategy", "symbol", "timeframe", "status", "created_at",
                                          "updated_at", "holdout_used", "params")}
                   | {"verdict": rep.get("verdict"), "insample": rep.get("insample"), "validation": rep.get("validation"),
                      "gate1": rep.get("gate1"), "holdout": rep.get("holdout")})
    return sorted(out, key=lambda e: e.get("updated_at") or "", reverse=True)


def create(name: str, strategy: str, symbol: str, timeframe: str, params: dict, report: dict | None = None,
           spec: dict | None = None, root: str = ROOT) -> dict:
    slug = re.sub(r"[^a-z0-9]+", "-", f"{strategy}-{symbol}-{timeframe}".lower()).strip("-")
    status = "backtested" if report else "draft"
    e = {
        "id": f"{slug}-{uuid.uuid4().hex[:6]}", "name": name or f"{strategy} {symbol} {timeframe}",
        "strategy": strategy, "symbol": symbol, "timeframe": timeframe, "params": params, "spec": spec,
        "status": status, "created_at": _now(), "updated_at": _now(), "holdout_used": False,
        "report": report, "versions": [{"v": 1, "params": params, "at": _now(),
                                        "data_version": (report or {}).get("data_version")}],
        "history": [{"status": status, "at": _now(), "note": "created" + (" with validation report" if report else "")}],
    }
    return save(e, root)


def allowed_next(e: dict) -> list[str]:
    s = e["status"]
    verdict = (e.get("report") or {}).get("verdict")
    out = []
    if s == "draft" and e.get("report"):
        out.append("backtested")
    if s == "backtested" and verdict == "pass":
        out.append("validated")
    if s == "validated":
        out.append("paper")
    if s != "retired":
        out.append("retired")
    return out


def promote(entry_id: str, to: str, note: str = "", root: str = ROOT) -> dict:
    e = get(entry_id, root)
    if to not in STATUSES:
        raise LifecycleError(f"unknown status '{to}'")
    if to == "live":
        raise LifecycleError("Live needs Gate 2: two months of paper trading on the finished execution system (Phase 5).")
    if to not in allowed_next(e):
        why = {"validated": "Gate 1 must pass first, including the one-time hold-out test.",
               "paper": "Only validated strategies can move to paper trading.",
               "backtested": "Run a backtest/validation first."}.get(to, "That step is not allowed from here.")
        raise LifecycleError(f"Cannot move from {e['status']} to {to}. {why}")
    e["status"] = to
    e["updated_at"] = _now()
    e["history"].append({"status": to, "at": _now(), "note": note})
    return save(e, root)


def record_holdout(entry_id: str, result: dict, gate_rows: list[dict], verdict: str, root: str = ROOT) -> dict:
    e = get(entry_id, root)
    first = not e.get("holdout_used")
    e["holdout_used"] = True
    e["report"]["holdout"] = result | {"run_at": _now(), "first_run": first}
    e["report"]["gate1"], e["report"]["verdict"] = gate_rows, verdict
    e["updated_at"] = _now()
    e["history"].append({"status": e["status"], "at": _now(),
                         "note": "hold-out test run" + ("" if first else " AGAIN (result no longer independent)")})
    return save(e, root)


def delete(entry_id: str, root: str = ROOT) -> None:
    _path(entry_id, root).unlink(missing_ok=False)
