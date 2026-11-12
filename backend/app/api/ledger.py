from fastapi import APIRouter, HTTPException, Query

from app.ledger import analytics, build
from app.ledger import sessions as sess_svc

router = APIRouter(prefix="/ledger")


def _filtered(desk: str | None, symbol: str | None, session_id: str | None, days: int, rebuild: bool = False):
    data = build.load_ledger(days=days, rebuild=rebuild)
    sessions = [s for s in data["sessions"]
                if (not desk or s["desk"] == desk) and (not symbol or s["symbol"] == symbol)
                and (not session_id or s["id"] == session_id)]
    ids = {s["id"] for s in sessions}
    trades = [t for t in data["trades"] if t["session_id"] in ids]
    return data, sessions, trades


def _session_or_404(data: dict, session_id: str) -> dict:
    s = next((x for x in data["sessions"] if x["id"] == session_id), None)
    if not s:
        raise HTTPException(404, f"unknown session '{session_id}'")
    return s


def _session_trades(data: dict, session_id: str) -> list[dict]:
    return [t for t in data["trades"] if t["session_id"] == session_id]


@router.get("/sessions")
def sessions(desk: str | None = None, symbol: str | None = None, status: str | None = None, include_archived: bool = False,
             days: int = Query(150, ge=30, le=730)) -> dict:
    data, sess, _ = _filtered(desk, symbol, None, days)
    as_of = max((analytics.trading_day(t["exit_ts"]) for t in data["trades"]), default=None)
    out = []
    for s in sess:
        state = sess_svc.current_state(s)
        if (status and state != status) or (state == "archived" and not include_archived and status != "archived"):
            continue
        out.append({**s, "status": state, "metrics": sess_svc.session_metrics(_session_trades(data, s["id"]), as_of)})
    return {"source": data["source"], "warning": data["warning"], "as_of": as_of.isoformat() if as_of else None, "sessions": out}


@router.post("/sessions/{session_id}/{action}")
def session_action(session_id: str, action: str, days: int = Query(150, ge=30, le=730)) -> dict:
    s = _session_or_404(build.load_ledger(days=days), session_id)
    try:
        return {"id": session_id, "status": sess_svc.apply_action(s, action)}
    except sess_svc.InvalidTransition as e:
        raise HTTPException(409, str(e)) from e


@router.get("/sessions/{session_id}/chart")
def session_chart(session_id: str, around: int | None = None, bars: int = Query(400, ge=50, le=1500), days: int = Query(150, ge=30, le=730)) -> dict:
    data = build.load_ledger(days=days)
    s = _session_or_404(data, session_id)
    trades = _session_trades(data, session_id)
    around_ts = None
    if around is not None:
        t = next((x for x in trades if x["id"] == around), None)
        if not t:
            raise HTTPException(404, f"unknown trade {around} in session")
        around_ts = t["entry_ts"]
    return {"source": data["source"], **sess_svc.session_chart(s, trades, around_ts, bars)}


@router.get("/trades/{trade_id}")
def trade_detail(trade_id: int, days: int = Query(150, ge=30, le=730)) -> dict:
    data = build.load_ledger(days=days)
    t = next((x for x in data["trades"] if x["id"] == trade_id), None)
    if not t:
        raise HTTPException(404, f"unknown trade {trade_id}")
    s = next(x for x in data["sessions"] if x["id"] == t["session_id"])
    return {"source": data["source"], "trade": sess_svc.enrich_trade(t), "session": {"id": s["id"], "name": s["name"], "desk": s["desk"]}}


@router.get("/trades")
def trades(desk: str | None = None, symbol: str | None = None, session_id: str | None = None, side: str | None = None,
           result: str | None = Query(None, pattern="^(win|loss)$"), day: str | None = None, q: str | None = None,
           basis: str = Query("exited", pattern="^(entered|exited)$"), days: int = Query(150, ge=30, le=730),
           limit: int = Query(200, ge=1, le=5000), offset: int = Query(0, ge=0)) -> dict:
    data, _, rows = _filtered(desk, symbol, session_id, days)
    key = "exit_ts" if basis == "exited" else "entry_ts"
    if side:
        rows = [r for r in rows if r["side"] == side]
    if result:
        rows = [r for r in rows if (r["pnl"] > 0) == (result == "win")]
    if day:
        rows = [r for r in rows if analytics.trading_day(r[key]).isoformat() == day]
    if q:
        needle = q.lower()
        rows = [r for r in rows if needle in f"{r['symbol']} {r['exit_reason']} {r['side']} {r['entry_ts'][:10]} {r['exit_ts'][:10]} {r['strategy']}".lower()]
    rows = sorted(rows, key=lambda r: r[key], reverse=True)
    return {"source": data["source"], "warning": data["warning"], "total": len(rows), "net": round(sum(r["pnl"] for r in rows), 2),
            "wins": int(sum(r["pnl"] > 0 for r in rows)), "trades": [sess_svc.enrich_trade(r) for r in rows[offset:offset + limit]]}


@router.get("/dashboard")
def dashboard(desk: str | None = None, symbol: str | None = None, days: int = Query(150, ge=30, le=730),
              rebuild: bool = False) -> dict:
    data, sess, rows = _filtered(desk, symbol, None, days, rebuild)
    capital = sum(s["initial_balance"] for s in sess)
    out = analytics.dashboard(rows, capital)
    out.update(source=data["source"], warning=data["warning"], built_at=data["built_at"],
               filters={"desk": desk, "symbol": symbol}, sessions=len(sess),
               available={"desks": build.DESKS, "symbols": build.DEFAULT_SYMBOLS},
               account=None)  # no broker connected: equity/margin/leverage unavailable (never faked)
    return out
