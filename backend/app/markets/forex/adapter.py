from __future__ import annotations

from datetime import datetime

from app.domain import Instrument, Market
from app.markets.base import MarketAdapter
from app.markets.forex.sessions import forex_market_open

_PAIRS = {
    "EURUSD": ("EUR_USD", 0.0001),
    "GBPUSD": ("GBP_USD", 0.0001),
    "USDJPY": ("USD_JPY", 0.01),
    "AUDUSD": ("AUD_USD", 0.0001),
    "XAUUSD": ("XAU_USD", 0.1),
}


class ForexAdapter(MarketAdapter):
    market = Market.FOREX

    def get_symbols(self) -> list[Instrument]:
        return [
            Instrument(
                market=Market.FOREX,
                symbol=sym,
                type="metal" if sym.startswith("XAU") else "forex",
                lot_size=100 if sym.startswith("XAU") else 100_000,
                pip_size=pip,
                broker_symbols={"oanda": oanda, "mt5": sym},
            )
            for sym, (oanda, pip) in _PAIRS.items()
        ]

    def is_open(self, ts: datetime) -> bool:
        return forex_market_open(ts)

    def spread_cost(self, symbol: str, spread_pips: float, qty: float) -> float:
        # Approximation assuming USD-quoted pairs: pip value = pip_size * lot_size * qty.
        inst = next(i for i in self.get_symbols() if i.symbol == symbol)
        return spread_pips * inst.pip_size * inst.lot_size * qty
