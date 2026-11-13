"""MT5 magic numbers: how a real trade is tied back to the strategy (and desk) that placed it.

Every order a strategy sends to MT5 must carry its magic number (Phase 5 execution uses this table).
Trades placed by hand in the terminal have magic 0 and show up under the "manual" desk.
Each desk owns a block of 1000 numbers, so new strategies just take the next free number in their block.
"""
from __future__ import annotations

STRATEGY_MAGIC: dict[str, int] = {
    "EMA-1": 1001,
    "EMA-2": 1002,
    "EMA-3": 1003,
    "CANDLE-1": 2001,
    "ICT-1": 3001,
    "ICT-2": 3002,
    "ICT-3": 3003,
    "ICT-4": 3004,
    "SMC-1": 4001,
    "SMC-2": 4002,
    "SMC-3": 4003,
}

DESK_RANGES: dict[str, tuple[int, int]] = {
    "manual": (0, 0),
    "ema": (1000, 1999),
    "candle": (2000, 2999),
    "ict": (3000, 3999),
    "smc": (4000, 4999),
}

_BY_MAGIC = {m: name for name, m in STRATEGY_MAGIC.items()}


def desk_of(magic: int) -> str | None:
    return next((d for d, (lo, hi) in DESK_RANGES.items() if lo <= magic <= hi), None)


def strategy_of(magic: int) -> str:
    if magic == 0:
        return "Manual"
    return _BY_MAGIC.get(magic, f"Magic {magic}")


def desk_magics(desk: str) -> dict:
    """Strategies registered for a desk, for display."""
    lo, hi = DESK_RANGES[desk]
    return {name: m for name, m in STRATEGY_MAGIC.items() if lo <= m <= hi}
