"""My Investment (doc 15): invested vs current value, TWR, XIRR, drawdown, allocation, capital ledger.

Source of truth is the broker's deal history (deposits/withdrawals = MT5 'balance' deals); the equity curve is the
daily closing balance rebuilt from deals, with today's point at live equity.
"""
from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from app.execution.magic import strategy_of

CASH_TYPES = ("balance", "credit", "bonus")


def xirr(flows: list[tuple[datetime, float]]) -> float | None:
    """Annualised money-weighted return. flows: (time, amount) with investments negative, value received positive."""
    if len(flows) < 2 or not any(a < 0 for _, a in flows) or not any(a > 0 for _, a in flows):
        return None
    t0 = min(t for t, _ in flows)
    yrs = [((t - t0).total_seconds() / (365.25 * 86400), a) for t, a in flows]
    if max(y for y, _ in yrs) < 1 / 365:
        return None  # less than a day of history: an annualised rate is meaningless

    def npv(r):
        return sum(a / (1 + r) ** y for y, a in yrs)

    lo, hi = -0.9999, 100.0
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        f = npv(mid)
        if abs(f) < 1e-9:
            break
        if f_lo * f < 0:
            hi = mid
        else:
            lo, f_lo = mid, f
    return round(mid, 6)


def daily_series(deals: list[dict], equity_now: float, now: datetime) -> pd.DataFrame:
    """Per day: closing balance and the cash that came in/out that day."""
    if not deals:
        return pd.DataFrame(columns=["balance", "cash"])
    df = pd.DataFrame(deals)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["amount"] = df["profit"] + df["commission"] + df["swap"] + df["fee"]
    df["cash"] = np.where(df["type"].isin(CASH_TYPES), df["profit"], 0.0)
    df["day"] = df["ts"].dt.floor("D")
    g = df.groupby("day").agg(amount=("amount", "sum"), cash=("cash", "sum"))
    days = pd.date_range(g.index.min(), pd.Timestamp(now).floor("D"), freq="D", tz="UTC")
    g = g.reindex(days, fill_value=0.0)
    g["balance"] = g["amount"].cumsum()
    g.loc[g.index[-1], "balance"] = equity_now  # today = live equity (includes floating P&L)
    return g[["balance", "cash"]]


def twr_index(daily: pd.DataFrame) -> pd.Series:
    """Time-weighted growth index (starts at 1): cash flows are assumed to arrive at the start of their day."""
    idx, level, prev = [], 1.0, None
    for bal, cash in zip(daily["balance"], daily["cash"], strict=True):
        if prev is not None and prev + cash > 0:
            level *= bal / (prev + cash)
        idx.append(level)
        prev = bal
    return pd.Series(idx, index=daily.index)


def summary(deals: list[dict], account: dict, closed: list[dict], now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    equity = float(account["equity"])
    cash = [d for d in deals if d["type"] in CASH_TYPES]
    deposits = sum(d["profit"] for d in cash if d["profit"] > 0)
    withdrawals = -sum(d["profit"] for d in cash if d["profit"] < 0)
    invested = deposits - withdrawals
    daily = daily_series(deals, equity, now)
    idx = twr_index(daily) if len(daily) else pd.Series(dtype=float)
    rets = idx.pct_change().dropna() if len(idx) > 1 else pd.Series(dtype=float)
    dd = (idx / idx.cummax() - 1).min() * 100 if len(idx) else 0.0
    flows = [(pd.Timestamp(d["ts"]).to_pydatetime(), -d["profit"]) for d in cash] + [(now, equity)]
    monthly = (idx.resample("ME").last().pct_change().dropna() * 100).round(2) if len(idx) > 31 else pd.Series(dtype=float)
    if len(idx) and len(monthly) == 0:
        monthly = pd.Series([(idx.iloc[-1] - 1) * 100], index=[idx.index[-1]]).round(2)
    trade_deals = [d for d in deals if d["type"] in ("buy", "sell")]
    by_strategy: dict[str, dict] = {}
    for t in closed:
        k = strategy_of(t.get("magic") or 0)
        e = by_strategy.setdefault(k, {"strategy": k, "trades": 0, "pnl": 0.0})
        e["trades"] += 1
        e["pnl"] = round(e["pnl"] + t["pnl"], 2)
    by_symbol: dict[str, float] = {}
    for t in closed:
        by_symbol[t["symbol"]] = round(by_symbol.get(t["symbol"], 0) + t["pnl"], 2)
    today = float(daily["balance"].iloc[-1] - (daily["balance"].iloc[-2] if len(daily) > 1 else invested) - daily["cash"].iloc[-1]) if len(daily) else 0.0
    return {
        "currency": account.get("currency", "USD"), "server": account.get("server"), "mode": account.get("mode"),
        "invested": round(invested, 2), "deposits": round(deposits, 2), "withdrawals": round(withdrawals, 2),
        "current_value": round(equity, 2), "net_profit": round(equity - invested, 2),
        "return_pct": round((equity - invested) / invested * 100, 2) if invested else None,
        "today_pnl": round(today, 2),
        "twr_pct": round((idx.iloc[-1] - 1) * 100, 2) if len(idx) else None,
        "xirr_pct": None if (x := xirr(flows)) is None else round(x * 100, 2),
        "max_drawdown_pct": round(float(dd), 2),
        "best_day_pct": round(float(rets.max() * 100), 2) if len(rets) else None,
        "worst_day_pct": round(float(rets.min() * 100), 2) if len(rets) else None,
        "costs": {"commission": round(sum(d["commission"] for d in trade_deals), 2),
                  "swap": round(sum(d["swap"] for d in trade_deals), 2), "fees": round(sum(d["fee"] for d in trade_deals), 2)},
        "curve": [{"t": str(t.date()), "balance": round(float(b), 2), "index": round(float(i), 5), "cash": round(float(c), 2)}
                  for t, b, i, c in zip(daily.index, daily["balance"], idx, daily["cash"], strict=True)],
        "monthly_pct": [{"month": str(t)[:7], "pct": float(v)} for t, v in monthly.items()],
        "by_strategy": sorted(by_strategy.values(), key=lambda e: -abs(e["pnl"])),
        "by_symbol": [{"symbol": k, "pnl": v} for k, v in sorted(by_symbol.items(), key=lambda kv: -abs(kv[1]))],
        "ledger": [{"ts": d["ts"], "type": "deposit" if d["profit"] > 0 else "withdrawal", "amount": d["profit"],
                    "comment": d.get("comment") or d["type"]} for d in cash],
        "as_of": now.isoformat(timespec="seconds"),
    }
