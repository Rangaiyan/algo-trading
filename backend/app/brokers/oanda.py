"""OANDA v20 broker. Phase 1 fills this in (data), Phase 5 (execution). See doc 6.4."""
from __future__ import annotations

from app.brokers.base import BrokerAdapter

PRACTICE_URL = "https://api-fxpractice.oanda.com"
LIVE_URL = "https://api-fxtrade.oanda.com"


def lots_to_units(lots: float, side_is_buy: bool) -> int:
    """OANDA orders are in units: 1 lot = 100,000 units; sell = negative."""
    units = round(lots * 100_000)
    return units if side_is_buy else -units


class OandaBroker(BrokerAdapter):
    name = "oanda"

    def __init__(self, token: str, account_id: str, practice: bool = True):
        self.token = token
        self.account_id = account_id
        self.base_url = PRACTICE_URL if practice else LIVE_URL

    def _todo(self):
        raise NotImplementedError("OandaBroker is implemented in Phase 1/5")

    connect = get_account = get_positions = get_candles = stream_prices = _todo  # type: ignore
    place_order = modify_order = cancel_order = close_position = _todo  # type: ignore
