"""Shared domain types used by markets, brokers, strategies and risk."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class Market(StrEnum):
    FOREX = "forex"
    INDIA = "india"


class Mode(StrEnum):
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


@dataclass(frozen=True)
class Instrument:
    market: Market
    symbol: str
    type: str = "forex"
    lot_size: float = 100_000
    tick_size: float = 0.00001
    pip_size: float = 0.0001
    broker_symbols: dict[str, str] = field(default_factory=dict)  # {"mt5": "EURUSD.m"}


@dataclass(frozen=True)
class Bar:
    ts: datetime  # UTC, bar open time
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    spread: float = 0.0


@dataclass(frozen=True)
class Signal:
    symbol: str
    side: Side
    entry: float | None  # None = market (fills at the next bar's open); a price = limit order
    stop_loss: float
    take_profit: float | None
    strategy: str
    reason: str = ""
    expires_bars: int = 20  # limit orders only: cancelled if not filled within this many bars


@dataclass
class Order:
    client_order_id: str  # unique, for idempotency
    symbol: str
    side: Side
    type: OrderType
    qty: float  # lots (MT5) - broker adapter converts to units where needed
    stop_loss: float  # mandatory: broker-side protection is always attached
    take_profit: float | None = None
    price: float | None = None


@dataclass
class OrderResult:
    ok: bool
    broker_order_id: str | None = None
    fill_price: float | None = None
    reason: str = ""


@dataclass
class Position:
    id: str
    symbol: str
    side: Side
    qty: float
    entry_price: float
    stop_loss: float | None
    take_profit: float | None
    unrealized_pnl: float = 0.0


@dataclass
class Account:
    broker: str
    currency: str
    balance: float
    equity: float
    margin_used: float = 0.0
