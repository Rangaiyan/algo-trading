"""MT5 broker: talks to the Windows MT5 Gateway over HTTP (doc 6.2).

Data side (Phase 1): account, positions, candles, polled prices.
Order side (Phase 5): place / cancel / close / modify through the gateway, which refuses non-demo accounts.
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime

import pandas as pd

from app.brokers.base import BrokerAdapter
from app.data.mt5_history import Gateway, GatewayError, to_frame
from app.domain import Account, Order, OrderResult, Position, Side


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

    # ---- execution (Phase 5): the gateway enforces demo-only, broker-side SL, idempotency ----
    def place_order(self, order: Order, magic: int = 0, expire_minutes: int | None = None) -> OrderResult:
        body = {"client_id": order.client_order_id, "symbol": order.symbol, "side": order.side.value,
                "type": order.type.value, "volume": order.qty, "price": order.price, "stop_loss": order.stop_loss,
                "take_profit": order.take_profit, "magic": magic, "expire_minutes": expire_minutes}
        try:
            r = self.gw.send("POST", "/orders", body)
        except GatewayError as e:
            return OrderResult(False, reason=str(e))
        self.last_result = r
        ticket = r.get("ticket") or r.get("order") or r.get("deal")
        return OrderResult(bool(r.get("ok")), str(ticket) if ticket else None, r.get("price"), r.get("reason", ""))

    def cancel_order(self, order_id: str) -> OrderResult:
        try:
            r = self.gw.send("DELETE", f"/orders/{order_id}")
        except GatewayError as e:
            return OrderResult(False, order_id, reason=str(e))
        return OrderResult(bool(r.get("ok")), order_id, None, r.get("reason", ""))

    def close_position(self, position_id: str) -> OrderResult:
        try:
            r = self.gw.send("POST", f"/positions/{position_id}/close", {})
        except GatewayError as e:
            return OrderResult(False, position_id, reason=str(e))
        return OrderResult(bool(r.get("ok")), position_id, r.get("price"), r.get("reason", ""))

    def modify_order(self, order_id: str, **changes) -> OrderResult:
        try:
            r = self.gw.send("POST", f"/positions/{order_id}/modify",
                             {"stop_loss": changes["stop_loss"], "take_profit": changes.get("take_profit")})
        except GatewayError as e:
            return OrderResult(False, order_id, reason=str(e))
        return OrderResult(bool(r.get("ok")), order_id, None, r.get("reason", ""))

    def pending_orders(self) -> list[dict]:
        return self.gw.get("/orders")
