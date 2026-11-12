"""Dashboard analytics over a list of trade rows. Pure functions, no I/O."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


def trading_day(ts_iso: str) -> date:
    """FX trading day rolls at 17:00 New York: 17:00 Sunday belongs to Monday."""
    ny = datetime.fromisoformat(ts_iso).astimezone(NY)
    return (ny + timedelta(hours=7)).date()


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _agg(rows: list[dict]) -> dict:
    pnls = [r["pnl"] for r in rows]
    wins = [p for p in pnls if p > 0]
    return {
        "pnl": round(sum(pnls), 2), "trades": len(rows),
        "win_rate": round(len(wins) / len(rows), 4) if rows else 0.0,
        "pips": round(sum(r["pips"] for r in rows), 1),
        "long_pnl": round(sum(r["pnl"] for r in rows if r["side"] == "buy"), 2),
        "short_pnl": round(sum(r["pnl"] for r in rows if r["side"] == "sell"), 2),
    }


def _run_stats(pnls: list[float]) -> tuple[int, int, int]:
    """(current streak signed: +wins / -losses, best win run, worst loss run)"""
    best_w = worst_l = cur = 0
    for p in pnls:
        if p > 0:
            cur = cur + 1 if cur > 0 else 1
            best_w = max(best_w, cur)
        else:
            cur = cur - 1 if cur < 0 else -1
            worst_l = max(worst_l, -cur)
    return cur, best_w, worst_l


def dashboard(trades: list[dict], initial_capital: float, as_of: date | None = None) -> dict:
    rows = sorted(trades, key=lambda r: r["exit_ts"])
    if not rows:
        return {"empty": True, "initial_capital": initial_capital}
    for r in rows:
        r["_day"] = trading_day(r["exit_ts"])
    by_day: dict[date, list[dict]] = defaultdict(list)
    for r in rows:
        by_day[r["_day"]].append(r)
    days = sorted(by_day)
    last_day = as_of or days[-1]

    day_pnl = {d: round(sum(x["pnl"] for x in by_day[d]), 2) for d in days}
    cum, run, hw, hw_day, low, low_day, deepest = [], 0.0, 0.0, days[0], 0.0, days[0], 0.0
    for d in days:
        run += day_pnl[d]
        cum.append({"date": d.isoformat(), "pnl": day_pnl[d], "cum": round(run, 2), "equity": round(initial_capital + run, 2),
                    "trades": len(by_day[d])})
        if run > hw:
            hw, hw_day = run, d
        if run < low:
            low, low_day = run, d
        deepest = min(deepest, run - hw)

    all_pnl = [r["pnl"] for r in rows]
    wins = [p for p in all_pnl if p > 0]
    losses = [p for p in all_pnl if p <= 0]
    gross_win, gross_loss = sum(wins), -sum(losses)
    costs = {k: round(sum(r[k] for r in rows), 2) for k in ("spread_cost", "slippage_cost", "commission", "swap")}
    total_costs = round(sum(costs.values()), 2)
    cur_streak, best_run, worst_run = _run_stats(all_pnl)
    worst_trade = min(rows, key=lambda r: r["pnl"])
    net = round(sum(all_pnl), 2)

    # today = most recent trading day; intraday high/low of the cumulative day line
    t_rows = by_day[last_day]
    t_run, t_hi, t_lo = 0.0, 0.0, 0.0
    t_hi_ts = None
    for r in sorted(t_rows, key=lambda x: x["exit_ts"]):
        t_run += r["pnl"]
        if t_run > t_hi:
            t_hi, t_hi_ts = t_run, r["exit_ts"]
        t_lo = min(t_lo, t_run)
    today = {**_agg(t_rows), "date": last_day.isoformat(), "high": round(t_hi, 2), "high_ts": t_hi_ts, "low": round(t_lo, 2),
             "kept_pct": round(t_run / t_hi * 100) if t_hi > 0 else None}

    def period(start: date, end: date) -> list[dict]:
        return [r for r in rows if start <= r["_day"] <= end]

    ws = _week_start(last_day)
    this_week, prev_week = period(ws, ws + timedelta(days=6)), period(ws - timedelta(days=7), ws - timedelta(days=1))
    ms = last_day.replace(day=1)
    pm_end = ms - timedelta(days=1)
    this_month, prev_month = period(ms, last_day), period(pm_end.replace(day=1), pm_end)
    wk_days = [{"day": (ws + timedelta(days=i)).strftime("%a").upper(), "pnl": day_pnl.get(ws + timedelta(days=i))} for i in range(5)]

    weeks = []
    for i in range(11, -1, -1):
        s = ws - timedelta(weeks=i)
        wr = period(s, s + timedelta(days=6))
        if wr:
            weeks.append({"start": s.isoformat(), **_agg(wr)})
    months = []
    first = ms
    for i in range(3, -1, -1):
        y, m = first.year, first.month - i
        while m <= 0:
            y, m = y - 1, m + 12
        s = date(y, m, 1)
        e = (date(y + (m == 12), m % 12 + 1, 1)) - timedelta(days=1)
        mr = period(s, e)
        if mr:
            months.append({"month": s.strftime("%b %y").upper(), **_agg(mr)})

    by_symbol = defaultdict(list)
    for r in rows:
        by_symbol[r["symbol"]].append(r)
    by_desk = defaultdict(list)
    for r in rows:
        by_desk[r["desk"]].append(r)

    def day_str(d):
        return d.isoformat()

    return {
        "empty": False, "initial_capital": initial_capital, "as_of": last_day.isoformat(),
        "career": {**_agg(rows), "since": days[0].isoformat(), "trading_days": len(days), "avg_day": round(net / len(days), 2),
                   "booked": net, "floating": 0.0, "open_positions": 0},
        "today": today,
        "week": {**_agg(this_week), "vs_last": round(sum(r["pnl"] for r in this_week) - sum(r["pnl"] for r in prev_week), 2), "days": wk_days},
        "month": {**_agg(this_month), "vs_last": round(sum(r["pnl"] for r in this_month) - sum(r["pnl"] for r in prev_month), 2)},
        "kpis": {
            "win_rate": round(len(wins) / len(rows), 4), "wins": len(wins), "losses": len(losses),
            "streak": cur_streak, "best_win_run": best_run, "worst_loss_run": worst_run,
            "avg_day": round(net / len(days), 2),
            "max_loss": {"pnl": round(worst_trade["pnl"], 2), "symbol": worst_trade["symbol"], "date": worst_trade["exit_ts"][:10]},
            "best_day": {"pnl": max(day_pnl.values()), "date": day_str(max(day_pnl, key=day_pnl.get))},
            "worst_day": {"pnl": min(day_pnl.values()), "date": day_str(min(day_pnl, key=day_pnl.get))},
            "deepest_dip": round(deepest, 2),
            "long_pnl": _agg(rows)["long_pnl"], "short_pnl": _agg(rows)["short_pnl"],
            "high_water": {"pnl": round(hw, 2), "date": day_str(hw_day)},
            "lowest": {"pnl": round(low, 2), "date": day_str(low_day)},
            "profit_factor": round(gross_win / gross_loss, 3) if gross_loss > 0 else None,
            "expectancy": round(net / len(rows), 2),
            "avg_win": round(gross_win / len(wins), 2) if wins else 0.0,
            "avg_loss": round(-gross_loss / len(losses), 2) if losses else 0.0,
            "costs": total_costs, "cost_breakdown": costs, "cost_per_trade": round(total_costs / len(rows), 2),
            "gross_before_costs": round(net + total_costs, 2),
            "avg_mfe_pips": round(sum(r["mfe_pips"] for r in rows) / len(rows), 1),
            "avg_mae_pips": round(sum(r["mae_pips"] for r in rows) / len(rows), 1),
            "avg_r": round(sum(r["r_multiple"] for r in rows) / len(rows), 3),
        },
        "days_last_30": [{"date": c["date"], "pnl": c["pnl"], "trades": c["trades"]} for c in cum[-30:]],
        "weeks_last_12": weeks, "months_last_4": months,
        "equity": cum,
        "by_symbol": {k: _agg(v) for k, v in sorted(by_symbol.items())},
        "by_desk": {k: _agg(v) for k, v in sorted(by_desk.items())},
    }
