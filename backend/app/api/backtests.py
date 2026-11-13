import threading
from datetime import UTC, datetime

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.backtest import runner
from app.data import mt5_history

router = APIRouter(prefix="/backtests")
data_router = APIRouter(prefix="/data")


class BacktestRequest(BaseModel):
    strategy: str
    symbol: str = "EURUSD"
    timeframe: str = "M15"
    source: str = Field("store", pattern="^(synthetic|store)$")  # synthetic is for tests only
    days: int = Field(0, ge=0, le=10000)  # 0 = all stored history (minus hold-out)
    params: dict = {}
    risk_pct: float = Field(0.5, gt=0, le=5)
    cost_stress: float = Field(1.0, ge=1.0, le=3.0)
    commission_per_lot: float = Field(0.0, ge=0)
    include_holdout: bool = False


@router.get("/strategies")
def list_strategies() -> list[dict]:
    return [{"id": k, "name": v.__doc__.strip().split("\n")[0] if v.__doc__ else k}
            for k, v in runner.STRATEGIES.items()]


@router.post("")
def create_backtest(req: BacktestRequest) -> dict:
    try:
        return runner.run(**req.model_dump())
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    except StopIteration as e:
        raise HTTPException(404, f"unknown symbol {req.symbol}") from e
    except FileNotFoundError as e:
        raise HTTPException(404, f"No downloaded {req.timeframe} data for {req.symbol}. "
                                 "Download it on the Data panel (or run backend/download_history.py).") from e


# ---------------- data store ----------------
_job: dict = {"running": False, "log": [], "started_at": None, "finished_at": None, "error": None}
_job_lock = threading.Lock()


class DownloadRequest(BaseModel):
    symbols: list[str] = mt5_history.SYMBOLS
    timeframes: list[str] = mt5_history.TIMEFRAMES
    years: float = Field(5, gt=0, le=20)


@data_router.get("/candles")
def data_candles(symbol: str, timeframe: str, end: datetime | None = None, start: datetime | None = None,
                 limit: int = Query(1500, ge=10, le=5000)) -> dict:
    """A window of stored candles for charts: bars in [start, end], or the last `limit` bars up to `end`."""
    from app.data import pipeline as P
    try:
        df = P.read_store(runner.DATA_ROOT, symbol, timeframe)
    except FileNotFoundError as e:
        raise HTTPException(404, f"No downloaded {timeframe} data for {symbol}") from e
    def utc(t: datetime) -> pd.Timestamp:
        ts = pd.Timestamp(t)
        return ts.tz_convert("UTC") if ts.tzinfo else ts.tz_localize("UTC")

    if end is not None:
        df = df[df.index <= utc(end)]
    if start is not None:
        df = df[df.index >= utc(start)]
    df = df.iloc[-limit:]
    return {
        "symbol": symbol, "timeframe": timeframe,
        "candles": [{"time": int(ts.timestamp()), "open": r.open, "high": r.high, "low": r.low, "close": r.close}
                    for ts, r in zip(df.index, df.itertuples(index=False), strict=True)],
    }


@data_router.get("/catalog")
def data_catalog() -> dict:
    return {"datasets": mt5_history.catalog(runner.DATA_ROOT), "job": {k: v for k, v in _job.items() if k != "log"},
            "log": _job["log"][-30:]}


@data_router.post("/download")
def data_download(req: DownloadRequest) -> dict:
    """Start (or top up) the history download in the background. Poll /data/catalog for progress."""
    with _job_lock:
        if _job["running"]:
            raise HTTPException(409, "a download is already running")
        _job.update(running=True, log=[], started_at=datetime.now(UTC).isoformat(), finished_at=None, error=None)

    def work():
        try:
            mt5_history.download_all(runner.DATA_ROOT, req.symbols, req.timeframes, req.years, log=_job["log"].append)
        except Exception as e:  # noqa: BLE001 - surface any failure to the UI
            _job["error"] = str(e)
        finally:
            _job.update(running=False, finished_at=datetime.now(UTC).isoformat())

    threading.Thread(target=work, daemon=True).start()
    return {"started": True}
