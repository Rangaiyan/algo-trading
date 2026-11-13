"""Phase 5 API: trading sessions, risk + kill switch, My Investment, reports."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from app.api.account import _fetch, closed_trades, summarize
from app.brokers.mt5 import MT5Broker
from app.core.config import get_settings
from app.data.mt5_history import GatewayError
from app.execution.commands import CommandHandler
from app.execution.engine import TradingEngine
from app.library import store
from app.portfolio.investment import summary as investment_summary
from app.reports import reports as R

router = APIRouter(tags=["trading"])
_engine: TradingEngine | None = None
LOOP_SECONDS = 15


def engine() -> TradingEngine:
    global _engine
    if _engine is None:
        if not get_settings().mt5_gateway_url:
            raise HTTPException(503, "MT5 is not set up (MT5_GATEWAY_URL is empty)")
        _engine = TradingEngine(MT5Broker())
    return _engine


def _live() -> dict:
    f = _fetch()
    if not f["connected"]:
        raise HTTPException(503, f.get("detail", "MT5 not connected"))
    return f


def _closed() -> list[dict]:
    return closed_trades(_live()["deals"] or [])


def _investment() -> dict:
    f = _live()
    return investment_summary(f["deals"] or [], f["account"], closed_trades(f["deals"] or []))


def _account_summary() -> dict:
    f = _fetch()
    if not f["connected"]:
        return f
    return summarize(f["account"], f["positions"], f["deals"], datetime.now(UTC))


def _report_text(period: str) -> str:
    f = _live()
    return R.summary_text(R.summarize(closed_trades(f["deals"] or []), f["account"], period))


def command_handler() -> CommandHandler:
    return CommandHandler(engine(), _account_summary, _closed, _investment, _report_text)


_singleton = None


def acquire_engine_lock(path: str = "runtime/engine.lock"):
    """Only ONE process may run the trading loop (a second backend copy must never trade in parallel).
    The OS releases the lock automatically when the process exits, even if it crashes."""
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    f = open(path, "a+")  # noqa: SIM115 - kept open for the life of the process
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    f.seek(0)
    f.truncate()
    f.write(str(os.getpid()))
    f.flush()
    return f


async def run_loop(notifier) -> None:
    """Background loop started by the app: one engine tick every LOOP_SECONDS, alerts to Telegram."""
    global _singleton
    _singleton = acquire_engine_lock()
    if _singleton is None:
        await notifier.send("⚠️ SYSTEM · a second Rinz backend tried to start the trading engine; it was blocked "
                            "(another process already runs it).", severity="warning")
        return
    eng = engine()
    while True:
        try:
            alerts = await asyncio.to_thread(eng.tick)
            for text, severity in alerts:
                await notifier.send(text, severity=severity)
        except Exception:  # noqa: BLE001 - the loop must survive anything
            pass
        await asyncio.sleep(LOOP_SECONDS)


# ---------------- sessions ----------------
class SessionIn(BaseModel):
    library_id: str | None = None
    strategy: str | None = None
    symbol: str | None = None
    timeframe: str | None = None
    params: dict = {}
    name: str = ""
    acknowledge_unvalidated: bool = False


class StatusIn(BaseModel):
    status: str


@router.get("/trading/status")
def trading_status() -> dict:
    eng = engine()
    out = eng.status()
    acc = _account_summary()
    out["account"] = acc
    out["risk"]["usage"] = eng.risk.usage(acc.get("equity")) if acc.get("connected") else {}
    out["loop_seconds"] = LOOP_SECONDS
    return out


@router.post("/trading/sessions")
def add_session(req: SessionIn) -> dict:
    eng = engine()
    if req.library_id:
        try:
            e = store.get(req.library_id)
        except KeyError as err:
            raise HTTPException(404, "unknown library entry") from err
        validated = e["status"] in ("paper", "validated")
        if not validated and not req.acknowledge_unvalidated:
            raise HTTPException(409, f"“{e['name']}” has not passed Gate 1 (status {e['status']}). Paper trading is for validated "
                                     "strategies; tick the shakedown box to run it anyway on the demo account.")
        strategy, symbol, tf, params = e["strategy"], e["symbol"], e["timeframe"], e["params"]
        mode, name = ("paper" if validated else "shakedown"), req.name or e["name"]
    else:
        if not (req.strategy and req.symbol and req.timeframe):
            raise HTTPException(422, "give a library_id, or strategy + symbol + timeframe")
        if not req.acknowledge_unvalidated:
            raise HTTPException(409, "Strategies that are not from the library (validated) can only run as a demo shakedown; "
                                     "tick the shakedown box to confirm.")
        strategy, symbol, tf, params, mode, name = req.strategy, req.symbol, req.timeframe, req.params, "shakedown", req.name
    try:
        return eng.add_session(strategy, symbol, tf, params, name=name, mode=mode, library_id=req.library_id)
    except (ValueError, StopIteration) as e:
        raise HTTPException(422, f"cannot create session: {e}") from e


@router.post("/trading/sessions/{sid}/status")
def session_status(sid: str, req: StatusIn) -> dict:
    try:
        return engine().set_status(sid, req.status)
    except KeyError as e:
        raise HTTPException(404, "unknown session") from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@router.delete("/trading/sessions/{sid}")
def delete_session(sid: str) -> dict:
    try:
        engine().remove_session(sid)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    return {"deleted": sid}


@router.post("/trading/tick")
def tick_now() -> dict:
    alerts = engine().tick()
    return {"alerts": [a for a, _ in alerts], "state": engine().state}


# ---------------- risk ----------------
class KillIn(BaseModel):
    confirm: str
    include_manual: bool = False


@router.get("/risk/config")
def risk_config() -> dict:
    return engine().risk.config.__dict__


@router.put("/risk/config")
def risk_update(patch: dict) -> dict:
    try:
        return engine().risk.update_config(patch).__dict__
    except (ValueError, TypeError) as e:
        raise HTTPException(422, str(e)) from e


@router.post("/risk/kill")
def kill(req: KillIn) -> dict:
    if req.confirm != "FLATTEN":
        raise HTTPException(422, 'type FLATTEN to confirm the kill switch')
    try:
        return engine().kill(include_manual=req.include_manual) | {"halted": True}
    except GatewayError as e:
        engine().risk.halt("kill", "kill switch pressed (broker unreachable)")
        raise HTTPException(502, f"Trading is halted, but positions could not be closed: {e}. Close them in MT5.") from e


@router.post("/risk/resume")
def resume() -> dict:
    eng = engine()
    eng.risk.resume("(from dashboard)")
    return {"halted": eng.risk.halted, "note": "Sessions stay paused; start each one again when you are ready."}


# ---------------- investment + reports ----------------
@router.get("/investment/summary")
def investment() -> dict:
    return _investment()


@router.get("/reports/summary")
def report_summary(period: str = "daily") -> dict:
    if period not in R.PERIODS:
        raise HTTPException(422, f"period must be one of {list(R.PERIODS)}")
    f = _live()
    s = R.summarize(closed_trades(f["deals"] or []), f["account"], period)
    return s | {"text": R.summary_text(s)}


@router.get("/reports/trades.csv", response_class=PlainTextResponse)
def report_trades(period: str = "all") -> PlainTextResponse:
    if period not in R.PERIODS:
        raise HTTPException(422, f"period must be one of {list(R.PERIODS)}")
    rows = R.period_trades(_closed(), period)
    return PlainTextResponse(R.trades_csv(rows), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="rinz-trades-{period}.csv"'})


@router.get("/reports/performance.html", response_class=HTMLResponse)
def report_html(period: str = "weekly") -> HTMLResponse:
    if period not in R.PERIODS:
        raise HTTPException(422, f"period must be one of {list(R.PERIODS)}")
    f = _live()
    closed = closed_trades(f["deals"] or [])
    eng = engine()
    s = R.summarize(closed, f["account"], period)
    risk = {"halt": eng.risk.state.get("halt") or "none", **{k: v for k, v in eng.risk.usage(f["account"]["equity"]).items() if k != "limits"}}
    return HTMLResponse(R.performance_html(s, investment_summary(f["deals"] or [], f["account"], closed), risk, eng.execution_quality()))
