from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

import pandas as pd

from app.domain import Account, Order, OrderResult, Position


class BrokerAdapter(ABC):
    """Unified broker interface (doc 6.3). The broker is the source of truth."""

    name: str

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def get_account(self) -> Account: ...

    @abstractmethod
    def get_positions(self) -> list[Position]: ...

    @abstractmethod
    def get_candles(self, symbol: str, timeframe: str, start, end) -> pd.DataFrame: ...

    @abstractmethod
    def stream_prices(self, symbols: list[str], callback: Callable) -> None: ...

    @abstractmethod
    def place_order(self, order: Order) -> OrderResult:
        """Must attach SL/TP broker-side."""

    @abstractmethod
    def modify_order(self, order_id: str, **changes) -> OrderResult: ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> OrderResult: ...

    @abstractmethod
    def close_position(self, position_id: str) -> OrderResult: ...
