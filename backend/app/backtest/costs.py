from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostConfig:
    spread_pips: float = 1.0          # used when the bar carries no recorded spread
    commission_per_lot: float = 0.0   # account currency, per lot, per side (MT5 raw-spread accounts ~3.5)
    slippage_pips: float = 0.1        # adverse, applied on market fills and on stop exits
    swap_long_per_lot: float = -3.0   # per lot per night (account currency)
    swap_short_per_lot: float = 0.5
    stress: float = 1.0               # Gate-1 cost stress: 1.5 = spread/slippage +50%

    def spread(self, bar_spread: float, pip_size: float) -> float:
        base = bar_spread if bar_spread > 0 else self.spread_pips * pip_size
        return base * self.stress

    def slippage(self, pip_size: float) -> float:
        return self.slippage_pips * pip_size * self.stress


def pnl_per_price_unit(symbol: str, lot_size: float, qty_lots: float, ref_price: float) -> float:
    """Account-currency (USD) PnL for a 1.0 move in price. USD-base pairs convert via price."""
    units = qty_lots * lot_size
    return units / ref_price if symbol.startswith("USD") else units
