from __future__ import annotations

import pandas as pd

from app.backtest.engine import BacktestConfig, run_backtest
from app.backtest.metrics import compute_metrics
from app.data import pipeline as P
from app.domain import Market
from app.markets.registry import get_market
from app.strategies.candle.strategies import CandlestickBaseline
from app.strategies.ema.strategies import EMACrossover, EMATrendPullback

STRATEGIES = {"EMA-1": EMATrendPullback, "EMA-2": EMACrossover, "CANDLE-1": CandlestickBaseline}
DATA_ROOT = "data_store"


def load_data(symbol: str, timeframe: str, source: str, days: int) -> pd.DataFrame:
    if source == "synthetic":
        return P.synthetic(days=days, timeframe=timeframe)
    return P.read_store(DATA_ROOT, symbol, timeframe)


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
    }


def run(strategy: str, symbol: str = "EURUSD", timeframe: str = "M15", source: str = "synthetic",
        days: int = 150, params: dict | None = None, risk_pct: float = 0.5, cost_stress: float = 1.0,
        commission_per_lot: float = 0.0) -> dict:
    if strategy not in STRATEGIES:
        raise KeyError(f"unknown strategy '{strategy}'")
    inst = next(i for i in get_market(Market.FOREX).get_symbols() if i.symbol == symbol)
    df = load_data(symbol, timeframe, source, days)
    cfg = BacktestConfig(risk_per_trade_pct=risk_pct)
    cfg.costs.stress, cfg.costs.commission_per_lot = cost_stress, commission_per_lot
    res = run_backtest(df, STRATEGIES[strategy](**(params or {})), inst, cfg)
    return {
        "equity": _equity_points(res.equity),
        "trades": [_trade_dict(t) for t in res.trades],
        "strategy": strategy, "symbol": symbol, "timeframe": timeframe, "source": source,
        "bars": len(df), "data_version": P.data_version(df),
        "range": [str(df.index[0]), str(df.index[-1])],
        "metrics": compute_metrics(res),
        "warning": "synthetic data: results are meaningless" if source == "synthetic" else None,
    }
