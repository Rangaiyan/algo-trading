from __future__ import annotations

import numpy as np
import pandas as pd

from app.backtest.engine import BacktestResult


def compute_metrics(res: BacktestResult) -> dict:
    t, eq, init = res.trades, res.equity, res.config.initial_balance
    pnls = np.array([x.pnl for x in t]) if t else np.array([])
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    gross_win, gross_loss = wins.sum(), -losses.sum()
    peak = eq.cummax()
    dd = (eq - peak) / peak
    daily = eq.resample("1D").last().dropna().pct_change().dropna()
    sharpe = float(daily.mean() / daily.std() * np.sqrt(252)) if len(daily) > 2 and daily.std() > 0 else 0.0
    downside = daily[daily < 0]
    sortino = (float(daily.mean() / downside.std() * np.sqrt(252))
               if len(downside) > 2 and downside.std() > 0 else 0.0)
    streak = longest = 0
    for p in pnls:
        streak = streak + 1 if p <= 0 else 0
        longest = max(longest, streak)
    final = float(eq.iloc[-1]) if len(eq) else init
    return {
        "trades": len(t),
        "net_profit": round(final - init, 2),
        "return_pct": round((final / init - 1) * 100, 2),
        "win_rate": round(len(wins) / len(t), 4) if t else 0.0,
        "avg_win": round(float(wins.mean()), 2) if len(wins) else 0.0,
        "avg_loss": round(float(losses.mean()), 2) if len(losses) else 0.0,
        "profit_factor": round(float(gross_win / gross_loss), 3) if gross_loss > 0 else None,
        "expectancy": round(float(pnls.mean()), 2) if len(pnls) else 0.0,
        "max_drawdown_pct": round(float(dd.min()) * 100, 2) if len(dd) else 0.0,
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "longest_losing_streak": longest,
        "total_fees": round(sum(x.fees for x in t), 2),
        "exit_reasons": pd.Series([x.exit_reason for x in t]).value_counts().to_dict() if t else {},
    }
