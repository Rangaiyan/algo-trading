"""MT5 Gateway (doc 6.2): small HTTP API in front of the local MT5 terminal.

Runs natively on Windows next to the MT5 terminal. The core backend talks to it over
HTTP with a bearer token and never imports MetaTrader5 itself.

All timestamps returned are UTC. MT5 reports bar/tick times in the broker's server clock,
so the server's UTC offset is detected from live ticks (or set via MT5_SERVER_UTC_OFFSET_HOURS).

Order endpoints are intentionally not implemented yet (Phase 5).
"""
from __future__ import annotations

import secrets
import hashlib
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import MetaTrader5 as mt5
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="MT5_", extra="ignore")

    terminal_path: str = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    gateway_token: str = ""
    # Leave empty to auto-detect from live ticks. Set e.g. 2 or 3 to force it.
    server_utc_offset_hours: float | None = None
    # SAFETY: orders are refused unless the logged-in account is a DEMO account. Only set this to true
    # after Gate 2 (paper trading) has passed and you have decided to trade real money.
    allow_live_orders: bool = False


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
            "max_bars": term.maxbars,  # caps how much history copy_rates_range can return
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
                "unrealized_pnl": p.profit, "opened_at": _to_utc(p.time), "magic": p.magic, "tag": p.comment,
                "swap": p.swap, "price_current": p.price_current,
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
            "currency_base": s.currency_base,
            # swap_mode 1 = points (most FX); values are per lot per night
            "swap_mode": s.swap_mode, "swap_long": s.swap_long, "swap_short": s.swap_short,
            "swap_rollover3days": s.swap_rollover3days,
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
        lo, hi = start.timestamp(), end.timestamp()
        # MT5 returns its oldest stored bar when the range lies before the available history;
        # drop anything outside the requested window so callers never get stray bars.
        return [
            {
                "ts": _to_utc(int(r["time"])), "open": float(r["open"]), "high": float(r["high"]),
                "low": float(r["low"]), "close": float(r["close"]),
                "volume": float(r["tick_volume"]), "spread": int(r["spread"]),
            }
            for r in rates
            if lo <= int(r["time"]) - off.total_seconds() <= hi
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


# ---------------- orders (Phase 5) ----------------
# Every order: demo-only guard, mandatory broker-side stop-loss, volume rounded to the broker's step,
# minimum stop distance respected, idempotent by client id (stored in the MT5 comment), retcode checked.

RETCODE_OK = {mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED, mt5.TRADE_RETCODE_DONE_PARTIAL}


class OrderIn(BaseModel):
    client_id: str = Field(..., min_length=4, max_length=60)   # unique per intended order (idempotency)
    symbol: str
    side: str = Field(..., pattern="^(buy|sell)$")
    type: str = Field("market", pattern="^(market|limit|stop)$")
    volume: float = Field(..., gt=0)
    price: float | None = None                                   # required for limit / stop
    stop_loss: float                                             # mandatory
    take_profit: float | None = None
    magic: int = 0
    deviation_points: int = 20
    expire_minutes: int | None = None                            # pending orders: cancel after this long


def _tag(client_id: str) -> str:
    """MT5 comments are short (31 chars): store a stable hash of the client id."""
    return "rz:" + hashlib.sha1(client_id.encode()).hexdigest()[:16]


def _demo_guard() -> None:
    acc = mt5.account_info()
    if acc is None:
        raise HTTPException(503, f"no account logged in: {mt5.last_error()}")
    if acc.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO and not settings.allow_live_orders:
        raise HTTPException(403, "Refused: the MT5 account is not a demo account and live orders are disabled "
                                 "(MT5_ALLOW_LIVE_ORDERS=false). Paper trading must pass Gate 2 first.")
    term = mt5.terminal_info()
    if term is None or not term.trade_allowed:
        raise HTTPException(409, "Algo Trading is switched off in the MT5 terminal (toolbar button). Turn it on.")


def _filling(info, pending: bool) -> int:
    if pending:
        return mt5.ORDER_FILLING_RETURN
    fm = int(getattr(info, "filling_mode", 0) or 0)
    if fm & 1:
        return mt5.ORDER_FILLING_FOK
    if fm & 2:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


def _volume(info, v: float) -> float:
    step = info.volume_step or 0.01
    v = int(v / step + 1e-9) * step
    v = min(v, info.volume_max)
    if v < info.volume_min:
        raise HTTPException(422, f"volume {v} below the broker minimum {info.volume_min}")
    return round(v, 8)


def _existing(tag: str) -> dict | None:
    """An order/position/deal already carrying this client tag (duplicate protection)."""
    for p in mt5.positions_get() or []:
        if p.comment == tag:
            return {"duplicate": True, "kind": "position", "ticket": p.ticket, "price": p.price_open, "volume": p.volume}
    for o in mt5.orders_get() or []:
        if o.comment == tag:
            return {"duplicate": True, "kind": "pending", "ticket": o.ticket, "price": o.price_open, "volume": o.volume_current}
    now = datetime.now(timezone.utc)
    for d in mt5.history_deals_get(now - timedelta(days=3), now + timedelta(days=1)) or []:
        if d.comment == tag and d.entry == mt5.DEAL_ENTRY_IN:
            return {"duplicate": True, "kind": "deal", "ticket": d.position_id, "price": d.price, "volume": d.volume}
    return None


def _result(r, t0: float, extra: dict) -> dict:
    if r is None:
        raise HTTPException(502, f"order_send returned nothing: {mt5.last_error()}")
    ok = r.retcode in RETCODE_OK
    out = {"ok": ok, "retcode": r.retcode, "broker_comment": r.comment, "order": r.order, "deal": r.deal,
           "price": r.price or extra.get("request_price"), "volume": r.volume,
           "latency_ms": round((time.perf_counter() - t0) * 1000, 1), **extra}
    if not ok:
        out["reason"] = f"rejected by broker: retcode {r.retcode} {r.comment}"
    return out


@app.post("/orders", dependencies=auth)
def place_order(o: OrderIn):
    t0 = time.perf_counter()
    with _lock:
        _ensure_connected()
        _demo_guard()
        info = _symbol(o.symbol)
        tag = _tag(o.client_id)
        dup = _existing(tag)
        if dup:
            return {"ok": True, **dup, "tag": tag}
        tick = mt5.symbol_info_tick(o.symbol)
        if tick is None:
            raise HTTPException(503, f"no price for {o.symbol} (market closed?)")
        buy = o.side == "buy"
        pending = o.type != "market"
        if pending and not o.price:
            raise HTTPException(422, "limit/stop orders need a price")
        price = o.price if pending else (tick.ask if buy else tick.bid)
        # stop-loss on the correct side, and at least the broker's minimum distance away
        if (buy and o.stop_loss >= price) or (not buy and o.stop_loss <= price):
            raise HTTPException(422, f"stop-loss {o.stop_loss} is on the wrong side of the entry {price}")
        min_dist = (info.trade_stops_level or 0) * info.point
        if abs(price - o.stop_loss) < min_dist or (o.take_profit and abs(o.take_profit - price) < min_dist):
            raise HTTPException(422, f"SL/TP closer than the broker minimum ({info.trade_stops_level} points)")
        if o.take_profit and ((buy and o.take_profit <= price) or (not buy and o.take_profit >= price)):
            raise HTTPException(422, f"take-profit {o.take_profit} is on the wrong side of the entry {price}")
        if pending:
            otype = {("buy", "limit"): mt5.ORDER_TYPE_BUY_LIMIT, ("sell", "limit"): mt5.ORDER_TYPE_SELL_LIMIT,
                     ("buy", "stop"): mt5.ORDER_TYPE_BUY_STOP, ("sell", "stop"): mt5.ORDER_TYPE_SELL_STOP}[(o.side, o.type)]
        else:
            otype = mt5.ORDER_TYPE_BUY if buy else mt5.ORDER_TYPE_SELL
        req = {
            "action": mt5.TRADE_ACTION_PENDING if pending else mt5.TRADE_ACTION_DEAL,
            "symbol": o.symbol, "volume": _volume(info, o.volume), "type": otype, "price": round(price, info.digits),
            "sl": round(o.stop_loss, info.digits), "tp": round(o.take_profit, info.digits) if o.take_profit else 0.0,
            "deviation": o.deviation_points, "magic": o.magic, "comment": tag,
            "type_time": mt5.ORDER_TIME_GTC, "type_filling": _filling(info, pending),
        }
        if pending and o.expire_minutes:
            exp = datetime.now(timezone.utc) + timedelta(minutes=o.expire_minutes)
            req["type_time"] = mt5.ORDER_TIME_SPECIFIED
            req["expiration"] = int(exp.timestamp() + _server_offset_seconds())
        r = mt5.order_send(req)
        return _result(r, t0, {"tag": tag, "request_price": req["price"], "spread_points": info.spread,
                               "requested_volume": o.volume})


@app.get("/orders", dependencies=auth)
def pending_orders():
    with _lock:
        _ensure_connected()
        return [
            {"ticket": o.ticket, "symbol": o.symbol, "type": o.type, "volume": o.volume_current, "price": o.price_open,
             "stop_loss": o.sl or None, "take_profit": o.tp or None, "magic": o.magic, "tag": o.comment,
             "placed_at": _to_utc(o.time_setup)}
            for o in (mt5.orders_get() or [])
        ]


@app.delete("/orders/{ticket}", dependencies=auth)
def cancel_order(ticket: int):
    t0 = time.perf_counter()
    with _lock:
        _ensure_connected()
        _demo_guard()
        r = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": ticket})
        return _result(r, t0, {"ticket": ticket})


class CloseIn(BaseModel):
    volume: float | None = None   # None = whole position
    deviation_points: int = 20


@app.post("/positions/{ticket}/close", dependencies=auth)
def close_position(ticket: int, body: CloseIn | None = None):
    t0 = time.perf_counter()
    body = body or CloseIn()
    with _lock:
        _ensure_connected()
        _demo_guard()
        pos = next(iter(mt5.positions_get(ticket=ticket) or []), None)
        if pos is None:
            raise HTTPException(404, f"no open position {ticket}")
        info = _symbol(pos.symbol)
        tick = mt5.symbol_info_tick(pos.symbol)
        buy = pos.type == mt5.POSITION_TYPE_BUY
        r = mt5.order_send({
            "action": mt5.TRADE_ACTION_DEAL, "position": ticket, "symbol": pos.symbol,
            "volume": _volume(info, body.volume or pos.volume), "type": mt5.ORDER_TYPE_SELL if buy else mt5.ORDER_TYPE_BUY,
            "price": tick.bid if buy else tick.ask, "deviation": body.deviation_points, "magic": pos.magic,
            "comment": pos.comment, "type_time": mt5.ORDER_TIME_GTC, "type_filling": _filling(info, False),
        })
        return _result(r, t0, {"ticket": ticket})


class ModifyIn(BaseModel):
    stop_loss: float
    take_profit: float | None = None


@app.post("/positions/{ticket}/modify", dependencies=auth)
def modify_position(ticket: int, body: ModifyIn):
    t0 = time.perf_counter()
    with _lock:
        _ensure_connected()
        _demo_guard()
        pos = next(iter(mt5.positions_get(ticket=ticket) or []), None)
        if pos is None:
            raise HTTPException(404, f"no open position {ticket}")
        r = mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "position": ticket, "symbol": pos.symbol,
                            "sl": body.stop_loss, "tp": body.take_profit or 0.0})
        return _result(r, t0, {"ticket": ticket})
