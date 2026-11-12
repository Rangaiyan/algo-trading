from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.domain import Instrument, Market


class MarketAdapter(ABC):
    """Hides all market differences (symbols, hours, costs, sizing). Doc section 4.2."""

    market: Market

    @abstractmethod
    def get_symbols(self) -> list[Instrument]: ...

    @abstractmethod
    def is_open(self, ts: datetime) -> bool:
        """Whether the market is tradable at this UTC timestamp."""

    @abstractmethod
    def spread_cost(self, symbol: str, spread_pips: float, qty: float) -> float:
        """Cost in account currency of crossing the spread (simplified; full CostModel in Phase 1)."""
