"""Demo ledger: runs our real strategies on synthetic data to produce sessions + trades.

This is NOT market history. It exists so the UI and analytics can be built end to end before
real data/paper trading exist. Every payload carries source="demo-synthetic".
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.backtest.engine import BacktestConfig, run_backtest
from app.data import pipeline as P
from app.domain import Market
from app.markets.registry import get_market
from app.strategies.candle.strategies import CandlestickBaseline
from app.strategies.ema.strategies import EMACrossover, EMATrendPullback

STRATEGIES = {"EMA-1": EMATrendPullback, "EMA-2": EMACrossover, "CANDLE-1": CandlestickBaseline}
DESK_OF = {"EMA-1": "ema", "EMA-2": "ema", "CANDLE-1": "candle"}
DESKS = ["ema", "ict", "smc", "candle"]  # ict/smc have no strategies yet (Phase 2)
DEFAULT_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY"]
INITIAL_BALANCE = 10_000.0
RISK_PCT = 0.5
CACHE_VERSION = "v2"
SETTINGS = {  # shown as chips on session cards
    "EMA-1": {"rr": 2.0, "atr_mult": 1.5, "trend": "EMA200"},
    "EMA-2": {"rr": 2.0, "atr_mult": 2.0, "adx_min": 20, "fast": 20, "slow": 50},
    "CANDLE-1": {"rr": 2.0, "sl_buffer_atr": 0.2, "trend": "EMA200"},
}
CACHE_DIR = Path("data_store")
_build_lock = threading.Lock()


def _trade_row(t, tid: int, session_id: str, desk: str) -> dict:
    d = asdict(t)
    d.update(
        id=tid, session_id=session_id, desk=desk, side=t.side.value,
        entry_ts=t.entry_ts.isoformat(), exit_ts=t.exit_ts.isoformat(),
    )
    for k, v in list(d.items()):
        if isinstance(v, float):
            d[k] = round(v, 5)
    return d


def build_ledger(days: int = 150, symbols: list[str] | None = None, start: str | None = None,
                 timeframe: str = "M15") -> dict:
    symbols = symbols or DEFAULT_SYMBOLS
    start = start or (datetime.now(UTC).date() - timedelta(days=days)).isoformat()
    insts = {i.symbol: i for i in get_market(Market.FOREX).get_symbols()}
    sessions, trades, tid = [], [], 1
    for si, sym in enumerate(symbols):
        gen = {"start": start, "days": days, "timeframe": timeframe, "seed": 11 + si * 7,
               "start_price": 150.0 if sym.endswith("JPY") else 1.1, "vol": 0.0004}
        df = P.synthetic(**gen)
        for sname, cls in STRATEGIES.items():
            sid = f"{DESK_OF[sname]}-{sname}-{sym}-{timeframe}".lower()
            res = run_backtest(df, cls(), insts[sym], BacktestConfig(initial_balance=INITIAL_BALANCE, risk_per_trade_pct=RISK_PCT))
            sessions.append({
                "id": sid, "name": f"{sname} · {sym} {timeframe}", "desk": DESK_OF[sname], "strategy": sname,
                "symbol": sym, "timeframe": timeframe, "mode": "demo", "status": "running",
                "initial_balance": INITIAL_BALANCE, "started_at": df.index[0].isoformat(),
                "data_version": P.data_version(df), "gen": gen, "risk_pct": RISK_PCT,
                "settings": SETTINGS[sname], "sides": "long+short",
            })
            for t in res.trades:
                trades.append(_trade_row(t, tid, sid, DESK_OF[sname]))
                tid += 1
    trades.sort(key=lambda r: r["exit_ts"])
    return {
        "source": "demo-synthetic",
        "warning": "Synthetic demo data from real strategy code. Not market history; not evidence of edge.",
        "built_at": datetime.now(UTC).isoformat(), "params": {"days": days, "symbols": symbols, "start": start},
        "sessions": sessions, "trades": trades,
    }


def load_ledger(days: int = 150, symbols: list[str] | None = None, rebuild: bool = False) -> dict:
    """Disk-cached per (UTC date, days, symbols) so the first request builds and the rest are instant."""
    symbols = symbols or DEFAULT_SYMBOLS
    key = f"demo_ledger_{CACHE_VERSION}_{datetime.now(UTC).date()}_{days}_{'-'.join(symbols)}.json"
    path = CACHE_DIR / key
    if path.exists() and not rebuild:
        return json.loads(path.read_text())
    requested_at = time.time()
    # One build at a time: a build takes ~1 min, and parallel requests (auto-refresh, other
    # pages) used to each start their own build and slow every one of them down.
    with _build_lock:
        if path.exists() and (not rebuild or path.stat().st_mtime >= requested_at):
            return json.loads(path.read_text())  # built by another request while we waited
        data = build_ledger(days, symbols)
        CACHE_DIR.mkdir(exist_ok=True)
        path.write_text(json.dumps(data))
        return data
