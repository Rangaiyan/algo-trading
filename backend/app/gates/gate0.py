"""Gate 0 (doc 2, 10.3 week 1, 21): cross-check the Rinz engine against MT5's Strategy Tester.

MT5 runs mt5-gateway/mql5/RinzGate0.mq5 and writes its closed trades to Common\\Files\\rinz_gate0_trades.csv.
We run the identical GATE0 strategy in our engine on the same symbol, timeframe and period, with costs set the
way the tester applies them (bid-price candles, recorded spreads, no extra slippage, fixed lots), then match
the trades one by one.
"""
from __future__ import annotations

import io
import os
from pathlib import Path

import numpy as np
import pandas as pd

from app.backtest import runner
from app.backtest.engine import run_backtest
from app.data import pipeline as P
from app.data.mt5_history import BAR_MINUTES, read_meta
from app.strategies.reference import Gate0Reference

DEFAULT_FILE = Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal" / "Common" / "Files" / "rinz_gate0_trades.csv"
TF_FROM_MT5 = {"PERIOD_M1": "M1", "PERIOD_M5": "M5", "PERIOD_M15": "M15", "PERIOD_M30": "M30", "PERIOD_H1": "H1",
               "PERIOD_H4": "H4", "PERIOD_D1": "D1"}
TOL = {"match_rate": 0.90, "count_diff": 0.05, "median_entry_pips": 1.0, "net_diff": 0.10, "pf_diff": 0.10}
WARMUP_BARS = 600
SL_REASON, TP_REASON = 4, 5  # MT5 DEAL_REASON_SL / DEAL_REASON_TP


def read_ea_csv(text: str, server_offset_hours: float = 0.0) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(text))
    if df.empty:
        raise ValueError("the EA file has no trades; run the Strategy Tester over a longer period")
    off = pd.Timedelta(hours=server_offset_hours)
    for col in ("open_time", "close_time"):
        df[col] = pd.to_datetime(df[col], unit="s", utc=True) - off  # tester times are broker-server time
    return df.sort_values("open_time").reset_index(drop=True)


def file_info(path: Path = DEFAULT_FILE) -> dict:
    if not path.exists():
        return {"path": str(path), "exists": False}
    st = path.stat()
    try:
        rows = max(0, len(path.read_text(errors="replace").strip().splitlines()) - 1)
    except OSError:
        rows = None
    return {"path": str(path), "exists": True, "modified": pd.Timestamp(st.st_mtime, unit="s", tz="UTC").isoformat(), "trades": rows}


def compare(text: str, server_offset_hours: float = 0.0) -> dict:
    ea = read_ea_csv(text, server_offset_hours)
    symbol, tf = str(ea["symbol"].iat[0]), TF_FROM_MT5.get(str(ea["timeframe"].iat[0]), str(ea["timeframe"].iat[0]))
    if tf not in BAR_MINUTES:
        raise ValueError(f"unsupported timeframe {ea['timeframe'].iat[0]}")
    params = {"fast": int(ea["fast"].iat[0]), "slow": int(ea["slow"].iat[0]),
              "sl_pips": float(ea["sl_pips"].iat[0]), "tp_pips": float(ea["tp_pips"].iat[0])}
    lots = float(ea["volume"].iat[0])
    bar = pd.Timedelta(minutes=BAR_MINUTES[tf])
    start = ea["open_time"].iat[0].floor(bar) - bar          # the signal bar of the EA's first trade
    end = ea["close_time"].iat[-1] + bar

    df = P.read_store(runner.DATA_ROOT, symbol, tf)
    meta = read_meta(runner.DATA_ROOT, symbol, tf)
    first = df.index.searchsorted(start)
    if first < WARMUP_BARS // 4 or df.index[-1] < ea["close_time"].iat[-1].floor(bar):
        raise ValueError(f"stored {symbol} {tf} data ({df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d}) does not cover the "
                         f"tester period {start:%Y-%m-%d} -> {end:%Y-%m-%d} plus warm-up; download more history or test a later period")
    window = df.iloc[max(0, first - WARMUP_BARS): df.index.searchsorted(end) + 1]
    cfg, _ = runner.make_config(meta, float(window.close.iloc[-1]))
    cfg.fixed_lots, cfg.costs.min_spread, cfg.costs.slippage_pips = lots, 0.0, 0.0   # as the tester does it
    inst = runner.instrument(symbol)
    res = run_backtest(window, Gate0Reference(**params, trade_from=str(start)), inst, cfg)
    ours = pd.DataFrame([{"side": t.side.value, "open_time": t.entry_ts, "open_price": t.entry_px, "close_time": t.exit_ts,
                          "close_price": t.exit_px, "pnl": t.pnl, "reason": t.exit_reason} for t in res.trades])
    if len(ours):
        ours = ours[(ours.open_time >= start) & (ours.open_time <= end)].reset_index(drop=True)

    pip = inst.pip_size
    used, matches = set(), []
    for k, e in ea.iterrows():
        cand = ours[(ours.side == e.side) & ((ours.open_time - e.open_time).abs() <= bar)] if len(ours) else ours
        cand = cand[~cand.index.isin(used)]
        if len(cand):
            j = (cand.open_time - e.open_time).abs().idxmin()
            used.add(j)
            o = ours.loc[j]
            ea_pnl = float(e.profit + e.swap + e.commission)
            matches.append({"ea": k, "ours": int(j), "side": e.side, "open_time": e.open_time.isoformat(),
                            "entry_diff_pips": round(float((o.open_price - e.open_price) / pip), 2),
                            "exit_diff_pips": round(float((o.close_price - e.close_price) / pip), 2),
                            "exit_bars_diff": round(float((o.close_time - e.close_time) / bar), 1),
                            "ea_reason": "sl" if e.reason == SL_REASON else "tp" if e.reason == TP_REASON else str(e.reason),
                            "our_reason": o.reason, "ea_pnl": round(ea_pnl, 2), "our_pnl": round(float(o.pnl), 2)})
    m = pd.DataFrame(matches)
    unmatched_ea = [{"side": e.side, "open_time": e.open_time.isoformat(), "open_price": e.open_price}
                    for k, e in ea.iterrows() if k not in set(m.get("ea", []))]
    unmatched_ours = [{"side": o.side, "open_time": o.open_time.isoformat(), "open_price": round(float(o.open_price), 5)}
                      for j, o in ours.iterrows() if j not in used]

    def pf(p):
        w, lo_ = p[p > 0].sum(), -p[p < 0].sum()
        return round(float(w / lo_), 3) if lo_ > 0 else None

    ea_p = ea.profit + ea.swap + ea.commission
    our_p = ours.pnl if len(ours) else pd.Series(dtype=float)
    n_ea, n_ours = len(ea), len(ours)
    match_rate = len(m) / max(n_ea, n_ours) if max(n_ea, n_ours) else 0.0
    gross = float(ea_p.abs().sum()) or 1.0
    net_diff = abs(float(our_p.sum()) - float(ea_p.sum())) / gross
    reason_agree = float((m.ea_reason == m.our_reason).mean()) if len(m) else 0.0
    med_entry = float(m.entry_diff_pips.abs().median()) if len(m) else None
    pf_ea, pf_ours = pf(ea_p), pf(our_p)
    checks = [
        {"check": "Trades matched one-to-one", "value": f"{match_rate:.0%} ({len(m)} of {max(n_ea, n_ours)})",
         "required": f">= {TOL['match_rate']:.0%}", "ok": match_rate >= TOL["match_rate"]},
        {"check": "Trade count", "value": f"MT5 {n_ea} vs Rinz {n_ours}", "required": f"within {TOL['count_diff']:.0%}",
         "ok": abs(n_ours - n_ea) <= max(1, TOL["count_diff"] * n_ea)},
        {"check": "Entry price (median difference)", "value": f"{med_entry} pips" if med_entry is not None else "—",
         "required": f"<= {TOL['median_entry_pips']} pip", "ok": med_entry is not None and med_entry <= TOL["median_entry_pips"]},
        {"check": "Net P&L", "value": f"MT5 ${float(ea_p.sum()):,.2f} vs Rinz ${float(our_p.sum()):,.2f}",
         "required": f"difference <= {TOL['net_diff']:.0%} of MT5 gross P&L", "ok": net_diff <= TOL["net_diff"]},
        {"check": "Profit factor", "value": f"MT5 {pf_ea} vs Rinz {pf_ours}", "required": f"within {TOL['pf_diff']}",
         "ok": pf_ea is not None and pf_ours is not None and abs(pf_ea - pf_ours) <= TOL["pf_diff"]},
    ]
    return {
        "symbol": symbol, "timeframe": tf, "params": params, "lots": lots, "period": [start.isoformat(), end.isoformat()],
        "server_offset_hours": server_offset_hours, "verdict": "pass" if all(c["ok"] for c in checks) else "fail",
        "checks": checks, "summary": {
            "ea_trades": n_ea, "our_trades": n_ours, "matched": len(m), "match_rate": round(match_rate, 3),
            "ea_net": round(float(ea_p.sum()), 2), "our_net": round(float(our_p.sum()), 2), "ea_pf": pf_ea, "our_pf": pf_ours,
            "exit_reason_agreement": round(reason_agree, 3), "median_entry_diff_pips": med_entry,
            "median_exit_diff_pips": float(m.exit_diff_pips.abs().median()) if len(m) else None,
            "same_bar_exit_share": round(float((m.exit_bars_diff.abs() < 1).mean()), 3) if len(m) else None},
        "unmatched_mt5": unmatched_ea[:50], "unmatched_rinz": unmatched_ours[:50],
        "largest_differences": sorted(matches, key=lambda r: -abs(r["our_pnl"] - r["ea_pnl"]))[:15],
        "notes": ["MT5 candles are bid prices: Rinz buys at bid + spread and exits on the bid, like the tester.",
                  "When a stop-loss and take-profit are both inside one candle, Rinz assumes the stop hit first (conservative); "
                  "the tester resolves it with 1-minute data, so a few exits can differ.",
                  "EMA warm-up differs slightly at the very start (MT5 seeds with a simple average); Rinz uses "
                  f"{WARMUP_BARS} warm-up bars before the period."],
        "tolerances": TOL, "costs": {"price_basis": cfg.costs.price_basis, "spread": "recorded per bar", "slippage": 0,
                                     "swap_long": cfg.costs.swap_long_per_lot, "swap_short": cfg.costs.swap_short_per_lot},
    }
