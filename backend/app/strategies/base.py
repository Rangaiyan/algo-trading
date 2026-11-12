from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain import Bar, Signal


class Strategy(ABC):
    """One interface for backtest, paper and live (doc 8)."""

    params: dict

    def __init__(self, **params):
        self.params = params

    def on_start(self, ctx) -> None:
        pass

    @abstractmethod
    def on_bar(self, ctx, bar: Bar) -> list[Signal]:
        """Called on a CLOSED bar only. Signals execute on the next available price."""

    def on_stop(self, ctx) -> None:
        pass
