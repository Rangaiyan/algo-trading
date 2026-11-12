"""MT5 broker: talks to the Windows MT5 Gateway over HTTP (doc 6.2). Implemented in Phase 1/5."""
from __future__ import annotations

from app.brokers.base import BrokerAdapter


class MT5Broker(BrokerAdapter):
    name = "mt5"

    def __init__(self, gateway_url: str, token: str):
        self.gateway_url = gateway_url
        self.token = token

    def _todo(self):
        raise NotImplementedError("MT5Broker is implemented in Phase 1/5")

    connect = get_account = get_positions = get_candles = stream_prices = _todo  # type: ignore
    place_order = modify_order = cancel_order = close_position = _todo  # type: ignore
