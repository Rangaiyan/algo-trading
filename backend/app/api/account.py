"""Live broker account (MT5 via the gateway): balance, equity, positions, realised P&L, and per-desk trades."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.execution.magic import DESK_RANGES, desk_magics, strategy_of

router = APIRouter(prefix="/account", tags=["account"])

EXIT_ENTRIES = ("out", "inout", "out_by")


def _net(d: dict) -> float:
    return d["profit"] + d["commission"] + d["swap"] + d["fee"]


def _get(client: httpx.Client, base: str, path: str):
    r = client.get(f"{base}{path}")
    if r.status_code == 401:
        raise HTTPException(502, "MT5 gateway rejected the token (MT5_GATEWAY_TOKEN mismatch)")
    if r.status_code == 404:
        return None  # endpoint not available on an older gateway
    if r.status_code != 200:
        raise HTTPException(502, f"MT5 gateway error {r.status_code}: {r.text[:200]}")
    return r.json()


def _fetch() -> dict:
    """Account, positions and deal history from the gateway, or {'connected': False, 'detail': ...}."""
    s = get_settings()
    if not s.mt5_gateway_url:
        return {"connected": False, "detail": "MT5 is not set up (MT5_GATEWAY_URL is empty)"}
    base = s.mt5_gateway_url.rstrip("/")
    try:
        with httpx.Client(timeout=8, headers={"Authorization": f"Bearer {s.mt5_gateway_token}"}) as client:
            account = _get(client, base, "/account")
            positions = _get(client, base, "/positions") or []
            deals = _get(client, base, "/deals")
    except httpx.HTTPError:
        return {"connected": False, "detail": "MT5 gateway not reachable. Start mt5-gateway/start.ps1 with the MT5 terminal open."}
    if account is None:
        return {"connected": False, "detail": "MT5 gateway has no /account endpoint"}
    return {"connected": True, "account": account, "positions": positions, "deals": deals}


def closed_trades(deals: list[dict]) -> list[dict]:
    """One row per closed position, newest first. P&L is the net of every deal in the position."""
    by_pos: dict[int, list[dict]] = {}
    for d in deals:
        if d["type"] in ("buy", "sell"):
            by_pos.setdefault(d["position_id"], []).append(d)
    out = []
    for pid, ds in by_pos.items():
        exits = [d for d in ds if d["entry"] in EXIT_ENTRIES]
        if not exits:
            continue
        entry = next((d for d in ds if d["entry"] == "in"), ds[0])
        last = max(exits, key=lambda d: d["ts"])
        magic = entry.get("magic", 0) or 0
        out.append({
            "position_id": pid, "symbol": entry["symbol"], "side": entry["type"],
            "volume": entry["volume"], "entry_price": entry["price"], "exit_price": last["price"],
            "opened_at": entry["ts"], "closed_at": last["ts"], "pnl": round(sum(_net(d) for d in ds), 2),
            "magic": magic, "strategy": strategy_of(magic),
        })
    out.sort(key=lambda t: t["closed_at"], reverse=True)
    return out


def summarize(account: dict, positions: list[dict], deals: list[dict] | None, now: datetime) -> dict:
    floating = sum(p.get("unrealized_pnl") or 0 for p in positions)
    equity, balance = account["equity"], account["balance"]
    margin = account.get("margin_used") or 0
    out = {
        "connected": True,
        "server": account.get("server"), "mode": account.get("mode"), "currency": account.get("currency", "USD"),
        "balance": balance, "equity": equity, "floating": round(floating, 2),
        "margin_used": margin, "free_margin": account.get("free_margin"),
        "margin_level": round(equity / margin * 100, 1) if margin else None,
        "leverage": account.get("leverage"),
        "positions": positions,
        "history_available": deals is not None,
    }
    if deals is None:
        return out

    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week0 = day0 - timedelta(days=day0.weekday())
    month0 = day0.replace(day=1)
    deposits = sum(d["profit"] for d in deals if d["type"] in ("balance", "credit", "bonus"))
    trade_deals = [d for d in deals if d["type"] in ("buy", "sell")]

    def realised(since: datetime | None) -> float:
        return round(sum(_net(d) for d in trade_deals if since is None or datetime.fromisoformat(d["ts"]) >= since), 2)

    # Running balance after every balance-changing deal (deposits and trade results), oldest first.
    running, balance_curve = 0.0, []
    for d in sorted(deals, key=lambda d: d["ts"]):
        if d["type"] in ("buy", "sell", "balance", "credit", "bonus"):
            running = round(running + _net(d), 2)
            balance_curve.append({"t": d["ts"], "balance": running})

    closed = closed_trades(deals)
    wins = sum(1 for t in closed if t["pnl"] > 0)
    total = realised(None)
    out.update({
        "deposits": round(deposits, 2),
        "pnl": {"today": realised(day0), "week": realised(week0), "month": realised(month0), "all": total},
        "total_pnl": round(total + floating, 2),
        "return_pct": round((equity - deposits) / deposits * 100, 2) if deposits else None,
        "trades": len(closed), "wins": wins, "losses": sum(1 for t in closed if t["pnl"] < 0),
        "win_rate": round(wins / len(closed), 4) if closed else None,
        "recent": closed[:15],
        "balance_curve": balance_curve[-500:],
    })
    return out


def desk_summary(desk: str, positions: list[dict], deals: list[dict] | None, currency: str = "USD") -> dict:
    lo, hi = DESK_RANGES[desk]
    mine = lambda m: lo <= (m or 0) <= hi  # noqa: E731
    trades = [t for t in closed_trades(deals or []) if mine(t["magic"])]
    open_pos = [{**p, "strategy": strategy_of(p.get("magic") or 0)} for p in positions if mine(p.get("magic"))]
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [t["pnl"] for t in trades if t["pnl"] < 0]
    gross_win, gross_loss = sum(wins), -sum(losses)

    strategies: dict[str, dict] = {name: {"strategy": name, "magic": m, "trades": 0, "net": 0.0, "wins": 0}
                                   for name, m in desk_magics(desk).items()}
    for t in trades:
        s = strategies.setdefault(t["strategy"], {"strategy": t["strategy"], "magic": t["magic"], "trades": 0, "net": 0.0, "wins": 0})
        s["trades"] += 1
        s["net"] = round(s["net"] + t["pnl"], 2)
        s["wins"] += t["pnl"] > 0
    for s in strategies.values():
        s["win_rate"] = round(s["wins"] / s["trades"], 4) if s["trades"] else None

    cum, curve = 0.0, []
    for t in sorted(trades, key=lambda t: t["closed_at"]):
        cum = round(cum + t["pnl"], 2)
        curve.append({"t": t["closed_at"], "cum": cum})

    return {
        "connected": True, "desk": desk, "currency": currency, "history_available": deals is not None,
        "magic_range": [lo, hi],
        "net": round(sum(t["pnl"] for t in trades), 2),
        "floating": round(sum(p.get("unrealized_pnl") or 0 for p in open_pos), 2),
        "trades": len(trades), "wins": len(wins), "losses": len(losses),
        "win_rate": round(len(wins) / len(trades), 4) if trades else None,
        "avg_win": round(gross_win / len(wins), 2) if wins else None,
        "avg_loss": round(-gross_loss / len(losses), 2) if losses else None,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else None,
        "best": max((t["pnl"] for t in trades), default=None),
        "worst": min((t["pnl"] for t in trades), default=None),
        "strategies": sorted(strategies.values(), key=lambda s: s["magic"]),
        "positions": open_pos, "closed": trades[:200], "curve": curve,
    }


@router.get("/live")
def live_account() -> dict:
    f = _fetch()
    if not f["connected"]:
        return f
    return summarize(f["account"], f["positions"], f["deals"], datetime.now(UTC))


@router.get("/desk/{desk}")
def desk_trades(desk: str) -> dict:
    if desk not in DESK_RANGES:
        raise HTTPException(404, f"unknown desk '{desk}'")
    f = _fetch()
    if not f["connected"]:
        return f
    return desk_summary(desk, f["positions"], f["deals"], f["account"].get("currency", "USD"))
