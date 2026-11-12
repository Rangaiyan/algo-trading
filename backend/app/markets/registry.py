from app.domain import Market
from app.markets.base import MarketAdapter
from app.markets.forex.adapter import ForexAdapter
from app.markets.india.adapter import IndiaAdapter

_ADAPTERS: dict[Market, MarketAdapter] = {
    Market.FOREX: ForexAdapter(),
    Market.INDIA: IndiaAdapter(),
}


def get_market(market: Market) -> MarketAdapter:
    return _ADAPTERS[market]


def market_status() -> list[dict]:
    return [
        {"market": m.value, "enabled": getattr(a, "enabled", True), "symbols": len(a.get_symbols())}
        for m, a in _ADAPTERS.items()
    ]
