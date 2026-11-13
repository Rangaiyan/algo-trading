"""MT5 broker: talks to the Windows MT5 Gateway over HTTP (doc 6.2).

Data side (Phase 1) is implemented: account, positions, candles, polled prices.
Order side (place/modify/cancel/close) is Phase 5 and still raises NotImplementedError.
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime

import pandas as pd

from app.brokers.base import BrokerAdapter
from app.data.mt5_history import Gateway, to_frame
from app.domain import Account, Position, Side


class MT5Broker(BrokerAdapter):
    name = "mt5"

    def __init__(self, gateway_url: str | None = None, token: str | None = None, gateway: Gateway | None = None):
        self.gw = gateway or Gateway(gateway_url, token, timeout=30)
        self._points: dict[str, float] = {}
        self._stop = threading.Event()

    def connect(self) -> None:
        st = self.gw.status()
        if not st.get("terminal_connected"):
            raise ConnectionError("MT5 terminal is not connected to the broker server")

    def get_account(self) -> Account:
        a = self.gw.get("/account")
        return Account(broker="mt5", currency=a["currency"], balance=a["balance"], equity=a["equity"],
                       margin_used=a.get("margin_used") or 0.0)

    def get_positions(self) -> list[Position]:
        return [
            Position(id=p["id"], symbol=p["symbol"], side=Side(p["side"]), qty=p["qty"], entry_price=p["entry_price"],
                     stop_loss=p.get("stop_loss"), take_profit=p.get("take_profit"),
                     unrealized_pnl=p.get("unrealized_pnl") or 0.0)
            for p in self.gw.get("/positions")
        ]

    def _point(self, symbol: str) -> float:
        if symbol not in self._points:
            self._points[symbol] = float(self.gw.symbol(symbol)["point"])
        return self._points[symbol]

    def get_candles(self, symbol: str, timeframe: str, start, end=None) -> pd.DataFrame:
        end = end or datetime.now(UTC)
        return to_frame(self.gw.candles(symbol, timeframe, start, end), self._point(symbol))

    def stream_prices(self, symbols: list[str], callback: Callable, interval: float = 1.0) -> None:
        """Poll /ticks and call `callback(symbol, tick)` on every change. Blocks until stop_stream()."""
        last: dict[str, dict] = {}
        self._stop.clear()
        while not self._stop.is_set():
            for sym, tick in self.gw.get("/ticks", symbols=",".join(symbols)).items():
                if tick and tick != last.get(sym):
                    last[sym] = tick
                    callback(sym, tick)
            self._stop.wait(interval)

    def stop_stream(self) -> None:
        self._stop.set()

    def _phase5(self, *_, **__):
        raise NotImplementedError("MT5 order execution is implemented in Phase 5 (demo first)")

    place_order = modify_order = cancel_order = close_position = _phase5  # type: ignore[assignment]
