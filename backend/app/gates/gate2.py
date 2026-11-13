"""Gate 2 (doc 11.2, 11.4, 11.5): is paper trading consistent with the backtest, and is the system reliable?

Evaluated per paper session from the engine's own order records (fills, closes, slippage, spread) against the
backtest expectations stored with the strategy's library entry (Gate 1 report), plus the failure-drill checklist.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from app.library import store

DRILLS = [
    ("kill_backend", "Kill the backend during an open trade: the SL/TP stays at the broker and the engine reconciles on restart"),
    ("disconnect", "Disconnect the internet / VPS: an alert arrives and the engine reconnects"),
    ("mt5_down", "Close or crash the MT5 terminal: a disconnect alert arrives and trading resumes when it is back"),
    ("rejected_order", "Force a broker rejection (invalid stops/volume): handled and alerted, no duplicate order"),
    ("daily_limit", "Trigger the daily loss limit: trading halts and an alert is sent"),
    ("kill_switch", "Press the kill switch (dashboard and Telegram): positions flattened, trading halted"),
    ("news", "A high-impact news event: the news filter blocks entries as configured"),
]
CRIT = {"weeks": 8, "trades": 30, "min_pf": 1.1, "pf_vs_backtest": 0.70, "win_rate_band": 0.15, "max_slippage_pips": 0.5}


class Drills:
    def __init__(self, root: str = "runtime"):
        self.path = Path(root) / "drills.json"
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {}

    def all(self) -> list[dict]:
        return [{"key": k, "drill": d, **self.state.get(k, {"done": False})} for k, d in DRILLS]

    def mark(self, key: str, done: bool, note: str = "") -> dict:
        if key not in dict(DRILLS):
            raise KeyError(key)
        self.state[key] = {"done": done, "note": note, "at": datetime.now(UTC).isoformat(timespec="seconds")}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, indent=1))
        return self.state[key]


def _metrics(closed: list[dict]) -> dict:
    pnl = np.array([o.get("pnl") or 0.0 for o in closed])
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    r = [o["pnl"] / o["risk_money"] for o in closed if o.get("risk_money")]
    holds = [(pd.Timestamp(o["closed_at"]) - pd.Timestamp(o.get("filled_at") or o["placed_at"])).total_seconds() / 3600
             for o in closed if o.get("closed_at")]
    cum = np.cumsum(pnl) if len(pnl) else np.array([0.0])
    return {"trades": len(closed), "net": round(float(pnl.sum()), 2),
            "win_rate": round(len(wins) / len(pnl), 3) if len(pnl) else None,
            "profit_factor": round(float(wins.sum() / -losses.sum()), 3) if len(losses) else None,
            "avg_r": round(float(np.mean(r)), 3) if r else None,
            "avg_hold_hours": round(float(np.mean(holds)), 1) if holds else None,
            "max_dd_money": round(float((cum - np.maximum.accumulate(np.r_[0.0, cum])[1:]).min()), 2)}


def _expected(session: dict) -> dict | None:
    """Backtest expectations from the library entry's Gate 1 report."""
    if not session.get("library_id"):
        return None
    try:
        rep = store.get(session["library_id"]).get("report") or {}
    except KeyError:
        return None
    ins, mc = rep.get("insample") or {}, rep.get("monte_carlo") or {}
    split = rep.get("split") or {}
    weeks = None
    if split.get("train") and split.get("validation"):
        weeks = (pd.Timestamp(split["validation"][1]) - pd.Timestamp(split["train"][0])).days / 7
    return {"profit_factor": ins.get("profit_factor"), "win_rate": ins.get("win_rate"), "trades": ins.get("trades"),
            "trades_per_week": round(ins["trades"] / weeks, 2) if weeks and ins.get("trades") else None,
            "mc_p95_dd_pct": (mc.get("max_dd_pct") or {}).get("p95")}


def evaluate(engine, equity: float | None, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    drills = Drills(str(engine.root)).all()
    drills_done = all(d["done"] for d in drills)
    issues = len(engine.state.get("issues") or [])
    out = []
    for s in engine.sessions:
        first = s.get("first_started_at") or s.get("started_at")
        if not first:
            continue
        mine = [o for o in engine.orders if o["session_id"] == s["id"]]
        closed = [o for o in mine if o["state"] == "closed"]
        m = _metrics(closed)
        weeks = (now - pd.Timestamp(first).to_pydatetime()).days / 7
        slips = [o["slippage_pips"] for o in mine if o.get("slippage_pips") is not None]
        spreads = [o["spread_pips"] for o in mine if o.get("spread_pips") is not None]
        exp = _expected(s)
        dd_pct = round(m["max_dd_money"] / equity * 100, 2) if equity else None
        rows = []

        def row(name, ok, value, need, pending=False):
            rows.append({"criterion": name, "status": "pending" if pending else ("pass" if ok else "fail"), "value": value, "required": need})

        row("Validated strategy (Gate 1)", s["mode"] == "paper", s["mode"], "paper session from a Gate-1-validated library entry")
        row("Duration", weeks >= CRIT["weeks"], f"{weeks:.1f} weeks", f">= {CRIT['weeks']} weeks", pending=weeks < CRIT["weeks"])
        row("Trades", m["trades"] >= CRIT["trades"], m["trades"], f">= {CRIT['trades']}", pending=m["trades"] < CRIT["trades"])
        if m["trades"] >= 5:
            pf_need = max(CRIT["min_pf"], CRIT["pf_vs_backtest"] * (exp or {}).get("profit_factor", 0) if exp and exp.get("profit_factor") else CRIT["min_pf"])
            row("Profit factor vs backtest", (m["profit_factor"] or 0) >= pf_need,
                f"paper {m['profit_factor']} vs backtest {(exp or {}).get('profit_factor', '—')}", f">= {pf_need:.2f}")
            if exp and exp.get("win_rate") is not None and m["win_rate"] is not None:
                row("Win rate vs backtest", abs(m["win_rate"] - exp["win_rate"]) <= CRIT["win_rate_band"],
                    f"paper {m['win_rate']:.0%} vs backtest {exp['win_rate']:.0%}", f"within {CRIT['win_rate_band']:.0%}")
            if exp and exp.get("mc_p95_dd_pct") is not None and dd_pct is not None:
                row("Drawdown within Monte Carlo range", abs(dd_pct) <= abs(exp["mc_p95_dd_pct"]),
                    f"{dd_pct}% vs backtest worst-5% {exp['mc_p95_dd_pct']}%", "inside the 95th percentile")
        else:
            row("Performance vs backtest", False, f"{m['trades']} closed trades", "needs at least 5 trades to compare", pending=True)
        avg_slip = round(float(np.mean(slips)), 2) if slips else None
        row("Execution: slippage", avg_slip is None or avg_slip <= CRIT["max_slippage_pips"],
            f"{avg_slip} pips avg" if avg_slip is not None else "no fills yet", f"<= {CRIT['max_slippage_pips']} pips (cost model)",
            pending=avg_slip is None)
        row("Reliability: reconciliation clean", issues == 0, f"{issues} open issue(s)", "0")
        row("Failure drills (plan 11.4)", drills_done, f"{sum(d['done'] for d in drills)} of {len(drills)} done", "all 7", pending=not drills_done)
        fail = any(r["status"] == "fail" for r in rows)
        verdict = "fail" if fail else "pending" if any(r["status"] == "pending" for r in rows) else "pass"
        out.append({"session": {k: s.get(k) for k in ("id", "name", "strategy", "symbol", "timeframe", "mode", "status", "library_id")},
                    "since": first, "weeks": round(weeks, 1), "paper": m, "expected": exp,
                    "execution": {"avg_slippage_pips": avg_slip, "avg_spread_pips": round(float(np.mean(spreads)), 2) if spreads else None,
                                  "rejected": sum(o["state"] == "rejected" for o in mine)},
                    "criteria": rows, "verdict": verdict})
    return {"sessions": out, "drills": drills, "criteria": CRIT, "as_of": now.isoformat(timespec="seconds")}
