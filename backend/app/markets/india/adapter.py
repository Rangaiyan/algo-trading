from __future__ import annotations

from datetime import datetime

from app.domain import Instrument, Market
from app.markets.base import MarketAdapter


class IndiaAdapter(MarketAdapter):
    """Placeholder. Indian market is enabled after Forex is proven (doc 1.4)."""

    market = Market.INDIA
    enabled = False

    def get_symbols(self) -> list[Instrument]:
        return []

    def is_open(self, ts: datetime) -> bool:
        return False

    def spread_cost(self, symbol: str, spread_pips: float, qty: float) -> float:
        raise NotImplementedError("Indian market is not implemented yet")
