from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.domain import Market
from app.markets.registry import get_market, market_status

router = APIRouter()


def system_status() -> dict:
    s = get_settings()
    return {
        "app": s.app_name,
        "environment": s.environment,
        "live_trading_enabled": s.live_trading_enabled,
        "markets": market_status(),
        "mode": "live" if s.live_trading_enabled else "demo",
        "brokers": [
            {"id": "mt5", "label": "MT5", "configured": bool(s.mt5_gateway_url), "connected": False},
            {"id": "oanda", "label": "OANDA", "configured": bool(s.oanda_token), "connected": False},
        ],
    }


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/status")
def status() -> dict:
    return system_status()


@router.get("/markets")
def markets() -> list[dict]:
    return market_status()


@router.get("/instruments")
def instruments(market: Market = Market.FOREX) -> list[dict]:
    adapter = get_market(market)
    if not getattr(adapter, "enabled", True):
        raise HTTPException(status_code=409, detail=f"market '{market.value}' is not enabled yet")
    return [i.__dict__ for i in adapter.get_symbols()]
