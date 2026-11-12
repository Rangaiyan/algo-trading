from __future__ import annotations

import itertools
from collections.abc import Callable

import pandas as pd

from app.brokers.base import BrokerAdapter
from app.domain import Account, Order, OrderResult, Position, Side


class SimulatedBroker(BrokerAdapter):
    """In-memory broker for backtests and tests. Market fills at the last set price."""

    name = "simulated"

    def __init__(self, balance: float = 10_000.0, currency: str = "USD"):
        self.balance = balance
        self.currency = currency
        self.prices: dict[str, float] = {}
        self._positions: dict[str, Position] = {}
        self._seen_client_ids: dict[str, OrderResult] = {}
        self._ids = itertools.count(1)

    def set_price(self, symbol: str, price: float) -> None:
        self.prices[symbol] = price

    def connect(self) -> None:
        return None

    def get_account(self) -> Account:
        unreal = sum(p.unrealized_pnl for p in self._positions.values())
        return Account(self.name, self.currency, self.balance, self.balance + unreal)

    def get_positions(self) -> list[Position]:
        return list(self._positions.values())

    def get_candles(self, symbol, timeframe, start, end) -> pd.DataFrame:
        raise NotImplementedError("SimulatedBroker is fed by the backtest engine")

    def stream_prices(self, symbols: list[str], callback: Callable) -> None:
        raise NotImplementedError

    def place_order(self, order: Order) -> OrderResult:
        # Duplicate-order protection (doc 13): same client_order_id returns the original result.
        if order.client_order_id in self._seen_client_ids:
            return self._seen_client_ids[order.client_order_id]
        if order.stop_loss is None:
            return OrderResult(False, reason="stop_loss is mandatory")
        px = self.prices.get(order.symbol)
        if px is None:
            return OrderResult(False, reason=f"no price for {order.symbol}")
        oid = str(next(self._ids))
        self._positions[oid] = Position(
            oid, order.symbol, order.side, order.qty, px, order.stop_loss, order.take_profit
        )
        result = OrderResult(True, oid, px)
        self._seen_client_ids[order.client_order_id] = result
        return result

    def modify_order(self, order_id: str, **changes) -> OrderResult:
        pos = self._positions.get(order_id)
        if not pos:
            return OrderResult(False, reason="unknown position")
        for k, v in changes.items():
            setattr(pos, k, v)
        return OrderResult(True, order_id)

    def cancel_order(self, order_id: str) -> OrderResult:
        return OrderResult(False, reason="no pending orders in simulator")

    def close_position(self, position_id: str) -> OrderResult:
        pos = self._positions.pop(position_id, None)
        if not pos:
            return OrderResult(False, reason="unknown position")
        px = self.prices[pos.symbol]
        direction = 1 if pos.side == Side.BUY else -1
        self.balance += (px - pos.entry_price) * direction * pos.qty * 100_000
        return OrderResult(True, position_id, px)
