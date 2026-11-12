"""Session metrics, lifecycle state, trade enrichment and chart data for the desk pages."""
from __future__ import annotations

import json
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

from app.data import pipeline as P
from app.domain import Market
from app.ledger.analytics import trading_day
from app.markets.registry import get_market

STATE_PATH = Path("data_store/session_state.json")
# action -> (allowed current states, new state). Demo state only; nothing here touches a broker.
TRANSITIONS = {
    "pause": ({"running"}, "paused"),
    "resume": ({"paused"}, "running"),
    "stop": ({"running", "paused"}, "stopped"),
    "archive": ({"stopped"}, "archived"),
}


class InvalidTransition(Exception):
    pass


def _load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def current_state(session: dict) -> str:
    return _load_state().get(session["id"], session["status"])


def apply_action(session: dict, action: str) -> str:
    if action not in TRANSITIONS:
        raise InvalidTransition(f"unknown action '{action}'")
    allowed, new = TRANSITIONS[action]
    cur = current_state(session)
    if cur not in allowed:
        raise InvalidTransition(f"cannot {action} a session that is {cur}")
    state = _load_state()
    state[session["id"]] = new
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state))
    return new


def session_metrics(trades: list[dict], as_of: date | None = None) -> dict:
    rows = sorted(trades, key=lambda r: r["exit_ts"])
    if not rows:
        return {"trades": 0, "net": 0.0, "booked": 0.0, "open": 0.0, "open_legs": 0, "peak": 0.0, "low": 0.0, "wins": 0, "losses": 0,
                "win_pct": 0.0, "per_trade": 0.0, "pips": 0.0, "today": None, "prev_day": None, "since": None}
    days = {r["exit_ts"]: trading_day(r["exit_ts"]) for r in rows}
    last_day = as_of or max(days.values())
    run = peak = low = 0.0
    for r in rows:
        run += r["pnl"]
        peak, low = max(peak, run), min(low, run)

    def day_block(d):
        rs = [r for r in rows if days[r["exit_ts"]] == d]
        if not rs:
            return None
        return {"date": d.isoformat(), "pnl": round(sum(r["pnl"] for r in rs), 2), "wins": int(sum(r["pnl"] > 0 for r in rs)),
                "losses": int(sum(r["pnl"] <= 0 for r in rs))}

    earlier = sorted({d for d in days.values() if d < last_day})
    wins = int(sum(r["pnl"] > 0 for r in rows))
    net = round(run, 2)
    return {
        "trades": len(rows), "net": net, "booked": net, "open": 0.0, "open_legs": 0, "peak": round(peak, 2), "low": round(low, 2),
        "wins": wins, "losses": len(rows) - wins, "win_pct": round(wins / len(rows), 4), "per_trade": round(net / len(rows), 2),
        "pips": round(sum(r["pips"] for r in rows), 1),
        "today": day_block(last_day), "prev_day": day_block(earlier[-1]) if earlier else None,
        "since": min(r["entry_ts"] for r in rows),
    }


@lru_cache(maxsize=32)
def _pip_size(symbol: str) -> float:
    inst = next((i for i in get_market(Market.FOREX).get_symbols() if i.symbol == symbol), None)
    return inst.pip_size if inst else 0.0001


def enrich_trade(t: dict) -> dict:
    """Derived fields for the trade-detail modal. Peak profit uses bid/ask excursions, so it already includes entry spread."""
    price_pnl = t["pnl"] + t["commission"] + t["swap"]          # result after spread+slippage, before commission & swap
    mfe = t["mfe_money"]
    held = (datetime.fromisoformat(t["exit_ts"]) - datetime.fromisoformat(t["entry_ts"])).total_seconds() / 60
    sign = 1 if t["side"] == "buy" else -1
    entry = t["entry_px"]
    planned = None
    if t.get("take_profit") and t.get("stop_loss") and entry != t["stop_loss"]:
        planned = round(abs(t["take_profit"] - entry) / abs(entry - t["stop_loss"]), 2)
    pip = _pip_size(t["symbol"])
    out = dict(t)
    out.update(
        peak_profit=round(mfe, 2), given_back=round(max(0.0, mfe - price_pnl), 2),
        kept_pct=round(max(0.0, price_pnl) / mfe * 100) if mfe > 0 else 0,
        held_minutes=round(held), overnight=trading_day(t["entry_ts"]) != trading_day(t["exit_ts"]),
        pip_size=pip, stop_pips=round(abs(entry - t["stop_loss"]) / pip, 1) if t.get("stop_loss") else None,
        target_pips=round(abs(t["take_profit"] - entry) / pip, 1) if t.get("take_profit") else None,
        best_price=round(entry + sign * t["mfe_pips"] * pip, 5), worst_price=round(entry - sign * t["mae_pips"] * pip, 5),
        planned_rr=planned, capture=round(t["pips"] / t["mfe_pips"], 3) if t["mfe_pips"] > 0 else None,
        total_costs=round(t["spread_cost"] + t["slippage_cost"] + t["commission"] + t["swap"], 2),
    )
    return out


@lru_cache(maxsize=16)
def _candles(start: str, days: int, timeframe: str, seed: int, start_price: float, vol: float):
    return P.synthetic(start=start, days=days, timeframe=timeframe, seed=seed, start_price=start_price, vol=vol)


def session_chart(session: dict, trades: list[dict], around_ts: str | None = None, bars: int = 400) -> dict:
    df = _candles(**{k: session["gen"][k] for k in ("start", "days", "timeframe", "seed", "start_price", "vol")})
    if around_ts:
        pos = int(df.index.searchsorted(datetime.fromisoformat(around_ts)))
        lo = max(0, pos - bars // 2)
    else:
        lo = max(0, len(df) - bars)
    win = df.iloc[lo:lo + bars]
    t0, t1 = win.index[0], win.index[-1]
    candles = [{"time": int(ts.timestamp()), "open": round(r.open, 5), "high": round(r.high, 5), "low": round(r.low, 5), "close": round(r.close, 5)}
               for ts, r in win.iterrows()]
    markers = []
    for t in trades:
        a, b = datetime.fromisoformat(t["entry_ts"]), datetime.fromisoformat(t["exit_ts"])
        if t0 <= a <= t1:
            markers.append({"time": int(a.timestamp()), "kind": "entry", "side": t["side"], "price": t["entry_px"], "trade_id": t["id"], "pnl": t["pnl"]})
        if t0 <= b <= t1:
            markers.append({"time": int(b.timestamp()), "kind": "exit", "side": t["side"], "price": t["exit_px"], "trade_id": t["id"],
                            "pnl": t["pnl"], "reason": t["exit_reason"]})
    markers.sort(key=lambda m: m["time"])
    return {"symbol": session["symbol"], "timeframe": session["timeframe"], "candles": candles, "markers": markers,
            "last_price": candles[-1]["close"], "bar_seconds": candles[1]["time"] - candles[0]["time"] if len(candles) > 1 else 0}
