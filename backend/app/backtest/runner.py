from __future__ import annotations

import pandas as pd

from app.backtest.costs import swap_from_spec
from app.backtest.engine import BacktestConfig, run_backtest
from app.backtest.metrics import compute_metrics
from app.data import pipeline as P
from app.data.mt5_history import read_meta
from app.domain import Market
from app.markets.registry import get_market
from app.strategies.candle.strategies import CandlestickBaseline
from app.strategies.ema.strategies import EMACrossover, EMARibbon, EMATrendPullback
from app.strategies.ict.strategies import ICTAsiaRaid, ICTOte, ICTSilverBullet
from app.strategies.rules import RuleStrategy
from app.strategies.smc.strategies import SMCBosRetest, SMCFvgMitigation, SMCSweepChoch

STRATEGIES = {
    "EMA-1": EMATrendPullback, "EMA-2": EMACrossover, "EMA-3": EMARibbon, "CANDLE-1": CandlestickBaseline,
    "SMC-1": SMCSweepChoch, "SMC-2": SMCBosRetest, "SMC-3": SMCFvgMitigation,
    "ICT-1": ICTAsiaRaid, "ICT-2": ICTOte, "ICT-3": ICTSilverBullet,
    "RULE": RuleStrategy,
}
DATA_ROOT = "data_store"


def load_data(symbol: str, timeframe: str, source: str, days: int, include_holdout: bool = False
              ) -> tuple[pd.DataFrame, dict | None]:
    """Candles plus the dataset's meta (None for synthetic).

    Real data excludes the hold-out block (the most recent months, doc 7.2) unless asked for, and
    `days` > 0 keeps only the last N days of what remains.
    """
    if source == "synthetic":
        return P.synthetic(days=days or 150, timeframe=timeframe), None
    df = P.read_store(DATA_ROOT, symbol, timeframe)
    meta = read_meta(DATA_ROOT, symbol, timeframe)
    if meta and not include_holdout:
        df = df[df.index < pd.Timestamp(meta["holdout_start"])]
    if days:
        df = df[df.index >= df.index[-1] - pd.Timedelta(days=days)]
    if df.empty:
        raise FileNotFoundError(f"no stored {timeframe} data for {symbol} in that range")
    return df, meta


def _equity_points(eq: pd.Series, max_points: int = 1000) -> list[dict]:
    dd = (eq - eq.cummax()) / eq.cummax() * 100  # on the FULL series so the true low survives
    step = -(-len(eq) // max_points)  # ceil: never exceeds max_points
    keep = eq.index[::step]
    return [
        {"t": ts.isoformat(), "equity": round(float(eq[ts]), 2), "dd": round(float(dd[ts]), 3)}
        for ts in keep
    ]


def _trade_dict(t) -> dict:
    return {
        "entry_ts": t.entry_ts.isoformat(), "exit_ts": t.exit_ts.isoformat(), "side": t.side.value,
        "qty": t.qty, "entry_px": round(t.entry_px, 5), "exit_px": round(t.exit_px, 5),
        "pnl": round(t.pnl, 2), "fees": round(t.fees, 2), "exit_reason": t.exit_reason,
        "stop_loss": round(t.stop_loss, 5) if t.stop_loss else None,
        "take_profit": round(t.take_profit, 5) if t.take_profit else None,
        "pips": round(t.pips, 1), "r_multiple": round(t.r_multiple, 2), "bars_held": t.bars_held,
        "mfe_pips": round(t.mfe_pips, 1), "mae_pips": round(t.mae_pips, 1), "session": t.entry_session,
    }


def instrument(symbol: str):
    return next(i for i in get_market(Market.FOREX).get_symbols() if i.symbol == symbol)


def make_config(meta: dict | None, ref_price: float, risk_pct: float = 0.5, cost_stress: float = 1.0,
                commission_per_lot: float = 0.0) -> tuple[BacktestConfig, dict | None]:
    """Backtest config with the broker's real costs from the dataset meta (swap, typical-spread floor)."""
    cfg = BacktestConfig(risk_per_trade_pct=risk_pct)
    cfg.costs.stress, cfg.costs.commission_per_lot = cost_stress, commission_per_lot
    spec = meta.get("spec") if meta else None
    swap = swap_from_spec(spec, ref_price)
    if swap:
        for k, v in swap.items():
            setattr(cfg.costs, k, v)
    if spec and spec.get("spread_points"):
        # floor at the broker's typical (live) spread: recorded bar spreads are per-bar minimums
        cfg.costs.min_spread = float(spec["spread_points"]) * float(spec["point"])
    return cfg, swap


def execute(strategy: str, inst, df: pd.DataFrame, meta: dict | None, params: dict | None = None, risk_pct: float = 0.5,
            cost_stress: float = 1.0, commission_per_lot: float = 0.0):
    """Backtest one strategy on an in-memory frame. Returns (BacktestResult, config, broker swap or None)."""
    if strategy not in STRATEGIES:
        raise KeyError(f"unknown strategy '{strategy}'")
    cfg, swap = make_config(meta, float(df.close.iloc[-1]), risk_pct, cost_stress, commission_per_lot)
    return run_backtest(df, STRATEGIES[strategy](**(params or {})), inst, cfg), cfg, swap


def run(strategy: str, symbol: str = "EURUSD", timeframe: str = "M15", source: str = "store",
        days: int = 0, params: dict | None = None, risk_pct: float = 0.5, cost_stress: float = 1.0,
        commission_per_lot: float = 0.0, include_holdout: bool = False) -> dict:
    if strategy not in STRATEGIES:
        raise KeyError(f"unknown strategy '{strategy}'")
    inst = instrument(symbol)
    df, meta = load_data(symbol, timeframe, source, days, include_holdout)
    res, cfg, swap = execute(strategy, inst, df, meta, params, risk_pct, cost_stress, commission_per_lot)
    return {
        "equity": _equity_points(res.equity),
        "trades": [_trade_dict(t) for t in res.trades],
        "strategy": strategy, "symbol": symbol, "timeframe": timeframe, "source": source,
        "bars": len(df), "data_version": P.data_version(df),
        "range": [str(df.index[0]), str(df.index[-1])],
        "holdout_start": meta["holdout_start"] if meta else None,
        "includes_holdout": bool(meta and include_holdout),
        "costs": {"spread": (f"recorded per bar, at least {round(cfg.costs.min_spread / inst.pip_size, 2)} pips"
                             if cfg.costs.min_spread else "recorded per bar") if meta else "synthetic",
                  "swap_long_per_lot": cfg.costs.swap_long_per_lot,
                  "swap_short_per_lot": cfg.costs.swap_short_per_lot, "swap_from_broker": bool(swap),
                  "commission_per_lot": commission_per_lot, "stress": cost_stress},
        "metrics": compute_metrics(res),
        "warning": "synthetic data: results are meaningless" if source == "synthetic"
        else "Includes the hold-out period: don't tune on this run" if include_holdout else None,
    }
