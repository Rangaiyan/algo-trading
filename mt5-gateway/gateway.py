"""MT5 Gateway (doc 6.2): small HTTP API in front of the local MT5 terminal.

Runs natively on Windows next to the MT5 terminal. The core backend talks to it over
HTTP with a bearer token and never imports MetaTrader5 itself.

All timestamps returned are UTC. MT5 reports bar/tick times in the broker's server clock,
so the server's UTC offset is detected from live ticks (or set via MT5_SERVER_UTC_OFFSET_HOURS).

Order endpoints are intentionally not implemented yet (Phase 5).
"""
from __future__ import annotations

import secrets
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import MetaTrader5 as mt5
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="MT5_", extra="ignore")

    terminal_path: str = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    gateway_token: str = ""
    # Leave empty to auto-detect from live ticks. Set e.g. 2 or 3 to force it.
    server_utc_offset_hours: float | None = None


settings = Settings()
_lock = threading.Lock()  # the MetaTrader5 package is not thread-safe
_offset_cache: dict[str, float] = {}

TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1, "MN1": mt5.TIMEFRAME_MN1,
}


def _ensure_connected() -> None:
    if mt5.terminal_info() is not None:
        return
    if not mt5.initialize(path=settings.terminal_path):
        raise HTTPException(503, f"MT5 initialize failed: {mt5.last_error()}")


def _server_offset_seconds() -> float:
    """Broker server time minus UTC, in seconds (rounded to 30 min)."""
    if settings.server_utc_offset_hours is not None:
        return settings.server_utc_offset_hours * 3600
    cached = _offset_cache.get("value")
    if cached is not None and time.time() - _offset_cache["at"] < 3600:
        return cached
    for sym in ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD"):
        tick = mt5.symbol_info_tick(sym)
        if tick is None:
            continue
        raw = tick.time - time.time()
        rounded = round(raw / 1800) * 1800
        if abs(raw - rounded) < 300:  # tick is fresh -> trustworthy
            _offset_cache.update(value=rounded, at=time.time())
            return rounded
    if cached is not None:
        return cached
    raise HTTPException(503, "Cannot detect server UTC offset (market closed?). "
                             "Set MT5_SERVER_UTC_OFFSET_HOURS in .env.")


def _to_utc(server_ts: int | float) -> str:
    utc = datetime.fromtimestamp(server_ts - _server_offset_seconds(), tz=timezone.utc)
    return utc.isoformat()


def _require_token(authorization: str = Header(default="")) -> None:
    expected = f"Bearer {settings.gateway_token}"
    if not settings.gateway_token or not secrets.compare_digest(authorization, expected):
        raise HTTPException(401, "invalid token")


def _symbol(name: str):
    info = mt5.symbol_info(name)
    if info is None:
        raise HTTPException(404, f"unknown symbol {name}")
    if not info.visible:
        mt5.symbol_select(name, True)
    return info


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not settings.gateway_token:
        raise RuntimeError("MT5_GATEWAY_TOKEN is empty - set it in mt5-gateway/.env")
    with _lock:
        mt5.initialize(path=settings.terminal_path)
    yield
    with _lock:
        mt5.shutdown()


app = FastAPI(title="Rinz MT5 Gateway", lifespan=lifespan)


@app.get("/health")
def health():
    with _lock:
        term = mt5.terminal_info()
        return {"ok": term is not None and term.connected,
                "terminal_connected": bool(term and term.connected)}


auth = [Depends(_require_token)]


@app.get("/status", dependencies=auth)
def status():
    with _lock:
        _ensure_connected()
        term, acc = mt5.terminal_info(), mt5.account_info()
        return {
            "terminal_connected": term.connected,
            "algo_trading_allowed": term.trade_allowed,
            "server": acc.server if acc else None,
            "account_mode": {0: "demo", 1: "contest", 2: "real"}.get(acc.trade_mode) if acc else None,
            "server_utc_offset_hours": _server_offset_seconds() / 3600,
        }


@app.get("/account", dependencies=auth)
def account():
    with _lock:
        _ensure_connected()
        acc = mt5.account_info()
        if acc is None:
            raise HTTPException(503, f"no account logged in: {mt5.last_error()}")
        return {
            "broker": "mt5", "login": acc.login, "server": acc.server,
            "mode": {0: "demo", 1: "contest", 2: "real"}.get(acc.trade_mode),
            "currency": acc.currency, "balance": acc.balance, "equity": acc.equity,
            "margin_used": acc.margin, "free_margin": acc.margin_free, "leverage": acc.leverage,
        }


@app.get("/positions", dependencies=auth)
def positions():
    with _lock:
        _ensure_connected()
        return [
            {
                "id": str(p.ticket), "symbol": p.symbol,
                "side": "buy" if p.type == mt5.POSITION_TYPE_BUY else "sell",
                "qty": p.volume, "entry_price": p.price_open,
                "stop_loss": p.sl or None, "take_profit": p.tp or None,
                "unrealized_pnl": p.profit, "opened_at": _to_utc(p.time), "magic": p.magic,
            }
            for p in (mt5.positions_get() or [])
        ]


@app.get("/symbols/{name}", dependencies=auth)
def symbol_info(name: str):
    with _lock:
        _ensure_connected()
        s = _symbol(name)
        return {
            "name": s.name, "digits": s.digits, "point": s.point,
            "contract_size": s.trade_contract_size, "volume_min": s.volume_min,
            "volume_max": s.volume_max, "volume_step": s.volume_step,
            "spread_points": s.spread, "currency_profit": s.currency_profit,
        }


@app.get("/candles", dependencies=auth)
def candles(
    symbol: str,
    timeframe: str = Query("H1", description=", ".join(TIMEFRAMES)),
    start: datetime = Query(..., description="UTC, ISO 8601"),
    end: datetime | None = Query(None, description="UTC, ISO 8601 (default: now)"),
):
    tf = TIMEFRAMES.get(timeframe.upper())
    if tf is None:
        raise HTTPException(400, f"timeframe must be one of {list(TIMEFRAMES)}")
    start = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
    end = end or datetime.now(timezone.utc)
    end = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
    with _lock:
        _ensure_connected()
        _symbol(symbol)
        off = timedelta(seconds=_server_offset_seconds())
        # MT5 interprets the range in server time
        rates = mt5.copy_rates_range(symbol, tf, start + off, end + off)
        if rates is None:
            raise HTTPException(502, f"copy_rates_range failed: {mt5.last_error()}")
        return [
            {
                "ts": _to_utc(int(r["time"])), "open": float(r["open"]), "high": float(r["high"]),
                "low": float(r["low"]), "close": float(r["close"]),
                "volume": float(r["tick_volume"]), "spread": int(r["spread"]),
            }
            for r in rates
        ]


@app.get("/ticks", dependencies=auth)
def ticks(symbols: str = Query(..., description="comma separated, e.g. EURUSD,GBPUSD")):
    out = {}
    with _lock:
        _ensure_connected()
        for name in [s.strip() for s in symbols.split(",") if s.strip()]:
            _symbol(name)
            t = mt5.symbol_info_tick(name)
            out[name] = None if t is None else {"ts": _to_utc(t.time), "bid": t.bid, "ask": t.ask}
    return out


DEAL_TYPES = {mt5.DEAL_TYPE_BUY: "buy", mt5.DEAL_TYPE_SELL: "sell", mt5.DEAL_TYPE_BALANCE: "balance",
              mt5.DEAL_TYPE_CREDIT: "credit", mt5.DEAL_TYPE_BONUS: "bonus"}
DEAL_ENTRIES = {mt5.DEAL_ENTRY_IN: "in", mt5.DEAL_ENTRY_OUT: "out", mt5.DEAL_ENTRY_INOUT: "inout",
                mt5.DEAL_ENTRY_OUT_BY: "out_by"}


@app.get("/deals", dependencies=auth)
def deals(
    start: datetime = Query(datetime(2000, 1, 1, tzinfo=timezone.utc), description="UTC, ISO 8601"),
    end: datetime | None = Query(None, description="UTC, ISO 8601 (default: now)"),
):
    """Account history: trades plus deposits/withdrawals (type 'balance'). Read-only."""
    start = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
    end = end or datetime.now(timezone.utc)
    end = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
    with _lock:
        _ensure_connected()
        # Pad by a day each side: MT5 filters in server time; we convert each deal to UTC below.
        rows = mt5.history_deals_get(start - timedelta(days=1), end + timedelta(days=1))
        if rows is None:
            raise HTTPException(502, f"history_deals_get failed: {mt5.last_error()}")
        try:
            off = _server_offset_seconds()
        except HTTPException:
            off = _offset_cache.get("value", 0.0)  # market closed and nothing cached: fall back to server time
        out = []
        for d in rows:
            ts = datetime.fromtimestamp(d.time - off, tz=timezone.utc)
            if not (start <= ts <= end):
                continue
            out.append({
                "ticket": d.ticket, "position_id": d.position_id, "ts": ts.isoformat(),
                "type": DEAL_TYPES.get(d.type, "other"), "entry": DEAL_ENTRIES.get(d.entry, "other"),
                "symbol": d.symbol, "volume": d.volume, "price": d.price,
                "profit": d.profit, "commission": d.commission, "swap": d.swap, "fee": d.fee,
                "magic": d.magic, "comment": d.comment,
            })
        return out


@app.post("/orders", dependencies=auth)
def place_order():
    raise HTTPException(501, "Order execution is implemented in Phase 5 (demo first).")
