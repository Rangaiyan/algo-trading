from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostConfig:
    spread_pips: float = 1.0          # used when the bar carries no recorded spread
    # MT5 bars record the MINIMUM spread seen during the bar, which understates what a market order pays.
    # The spread charged is never below this floor (price units; 0 = no floor). Set from the broker's typical spread.
    min_spread: float = 0.0
    commission_per_lot: float = 0.0   # account currency, per lot, per side (MT5 raw-spread accounts ~3.5)
    slippage_pips: float = 0.1        # adverse, applied on market fills and on stop exits
    swap_long_per_lot: float = -3.0   # per lot per night (account currency)
    swap_short_per_lot: float = 0.5
    triple_swap_weekday: int = 2      # Python weekday (Mon=0) whose rollover is charged x3; FX = Wednesday
    stress: float = 1.0               # Gate-1 cost stress: 1.5 = spread/slippage +50%

    def spread(self, bar_spread: float, pip_size: float) -> float:
        base = bar_spread if bar_spread > 0 else self.spread_pips * pip_size
        return max(base, self.min_spread) * self.stress

    def slippage(self, pip_size: float) -> float:
        return self.slippage_pips * pip_size * self.stress


def swap_from_spec(spec: dict, price: float) -> dict | None:
    """Broker swap (MT5 symbol spec) -> CostConfig swap fields in account currency (USD) per lot per night.

    Only "points" mode (swap_mode 1, used for FX and metals on most MT5 brokers) is converted;
    other modes return None so the defaults stay in place.
    """
    if not spec or spec.get("swap_mode") != 1:
        return None
    per_point = float(spec["point"]) * float(spec["contract_size"])  # profit-currency value of 1 point, 1 lot
    if spec.get("currency_profit", "USD") != "USD":
        per_point /= price  # e.g. USDJPY: JPY -> USD at the current rate
    mt5_day = int(spec.get("swap_rollover3days", 3))  # MT5: 0 = Sunday
    return {
        "swap_long_per_lot": round(float(spec["swap_long"]) * per_point, 4),
        "swap_short_per_lot": round(float(spec["swap_short"]) * per_point, 4),
        "triple_swap_weekday": (mt5_day - 1) % 7,
    }


def pnl_per_price_unit(symbol: str, lot_size: float, qty_lots: float, ref_price: float) -> float:
    """Account-currency (USD) PnL for a 1.0 move in price. USD-base pairs convert via price."""
    units = qty_lots * lot_size
    return units / ref_price if symbol.startswith("USD") else units
