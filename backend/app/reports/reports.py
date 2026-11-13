"""Reports (doc 16): trade history CSV, period summaries (daily/weekly/monthly) and a printable HTML performance report.

Every report states the account, mode, period, currency, that P&L is net of costs, when it was generated, and the
disclaimer from the plan.
"""
from __future__ import annotations

import csv
import html
import io
from datetime import UTC, datetime, timedelta

import pandas as pd

from app.execution.magic import strategy_of

DISCLAIMER = "Backtested and past performance do not guarantee future results. This is not investment or tax advice."
PERIODS = {"daily": 1, "weekly": 7, "monthly": 30, "all": 36500}


def period_trades(closed: list[dict], period: str, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(UTC)
    since = now - timedelta(days=PERIODS[period])
    return [t for t in closed if pd.Timestamp(t["closed_at"]) >= pd.Timestamp(since)]


def trades_csv(closed: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["closed_at_utc", "opened_at_utc", "strategy", "magic", "symbol", "side", "lots", "entry", "exit",
                "pnl_net_usd", "position_id"])
    for t in sorted(closed, key=lambda x: x["closed_at"]):
        w.writerow([t["closed_at"], t["opened_at"], strategy_of(t.get("magic") or 0), t.get("magic") or 0, t["symbol"],
                    t["side"], t["volume"], t["entry_price"], t["exit_price"], t["pnl"], t["position_id"]])
    return buf.getvalue()


def summarize(closed: list[dict], account: dict, period: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    ts = period_trades(closed, period, now)
    pnl = [t["pnl"] for t in ts]
    wins, losses = [p for p in pnl if p > 0], [p for p in pnl if p < 0]
    by_strategy: dict[str, dict] = {}
    for t in ts:
        k = strategy_of(t.get("magic") or 0)
        e = by_strategy.setdefault(k, {"strategy": k, "trades": 0, "pnl": 0.0, "wins": 0})
        e["trades"] += 1
        e["pnl"] = round(e["pnl"] + t["pnl"], 2)
        e["wins"] += t["pnl"] > 0
    by_symbol: dict[str, dict] = {}
    for t in ts:
        e = by_symbol.setdefault(t["symbol"], {"symbol": t["symbol"], "trades": 0, "pnl": 0.0})
        e["trades"] += 1
        e["pnl"] = round(e["pnl"] + t["pnl"], 2)
    return {
        "period": period, "from": (now - timedelta(days=PERIODS[period])).isoformat(timespec="minutes") if period != "all" else None,
        "to": now.isoformat(timespec="minutes"), "account": account.get("server"), "mode": account.get("mode"),
        "currency": account.get("currency", "USD"), "equity": account.get("equity"), "balance": account.get("balance"),
        "trades": len(ts), "net_pnl": round(sum(pnl), 2), "wins": len(wins), "losses": len(losses),
        "win_rate": round(len(wins) / len(ts), 3) if ts else None,
        "profit_factor": round(sum(wins) / -sum(losses), 2) if losses else None,
        "best": max(pnl, default=None), "worst": min(pnl, default=None),
        "by_strategy": sorted(by_strategy.values(), key=lambda e: -e["pnl"]),
        "by_symbol": sorted(by_symbol.values(), key=lambda e: -e["pnl"]),
        "generated_at": now.isoformat(timespec="seconds"), "net_of_costs": True, "disclaimer": DISCLAIMER,
    }


def summary_text(s: dict) -> str:
    pf = s["profit_factor"]
    lines = [f"📊 {s['period'].upper()} REPORT · {s['account']} ({(s['mode'] or '').upper()})",
             f"Trades: {s['trades']} ({s['wins']} won / {s['losses']} lost)",
             f"Net P&L: {'+' if s['net_pnl'] >= 0 else ''}${s['net_pnl']:,.2f} · PF {pf if pf is not None else '—'}",
             f"Equity: ${float(s['equity'] or 0):,.2f}"]
    for e in s["by_strategy"][:6]:
        lines.append(f"  {e['strategy']}: {e['trades']} trades, {'+' if e['pnl'] >= 0 else ''}${e['pnl']:,.2f}")
    return "\n".join(lines)


def performance_html(s: dict, inv: dict | None, risk: dict | None, execution: dict | None) -> str:
    e = html.escape

    def table(rows, cols):
        head = "".join(f"<th>{e(c)}</th>" for c in cols)
        body = "".join("<tr>" + "".join(f"<td>{e(str(r.get(c, '')))}</td>" for c in cols) + "</tr>" for r in rows)
        return f"<table><thead><tr>{head}</tr></thead><tbody>{body or '<tr><td colspan=9>none</td></tr>'}</tbody></table>"

    kv = lambda d: "".join(f"<tr><th>{e(str(k))}</th><td>{e(str(v))}</td></tr>" for k, v in d.items())  # noqa: E731
    inv_part = ""
    if inv:
        inv_part = "<h2>Investment</h2><table>" + kv({
            "Invested": inv["invested"], "Current value": inv["current_value"], "Net profit": inv["net_profit"],
            "Return %": inv["return_pct"], "TWR %": inv["twr_pct"], "XIRR %": inv["xirr_pct"],
            "Max drawdown %": inv["max_drawdown_pct"]}) + "</table>"
    risk_part = f"<h2>Risk</h2><table>{kv(risk)}</table>" if risk else ""
    ex_part = f"<h2>Execution quality</h2><table>{kv(execution)}</table>" if execution else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Rinz Algo {e(s['period'])} report</title>
<style>body{{font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:900px;margin:32px auto;padding:0 16px;color:#111}}
h1{{font-size:22px}}h2{{font-size:16px;margin-top:28px;border-bottom:1px solid #ddd;padding-bottom:4px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{border:1px solid #e3e3e3;padding:6px 8px;text-align:left}}
th{{background:#f6f6f6}}.meta{{color:#555;font-size:13px}}.disc{{margin-top:32px;color:#666;font-size:12px}}
@media print{{body{{margin:0}}}}</style></head><body>
<h1>Rinz Algo · {e(s['period'].title())} performance report</h1>
<p class="meta">Account {e(str(s['account']))} · mode {e(str(s['mode']).upper())} · currency {e(s['currency'])} ·
period {e(str(s['from'] or 'all time'))} → {e(s['to'])} UTC · figures are net of costs · generated {e(s['generated_at'])} UTC</p>
<h2>Summary</h2><table>{kv({"Trades": s['trades'], "Net P&L": s['net_pnl'], "Win rate": s['win_rate'], "Profit factor": s['profit_factor'],
"Best trade": s['best'], "Worst trade": s['worst'], "Equity": s['equity'], "Balance": s['balance']})}</table>
<h2>By strategy</h2>{table(s['by_strategy'], ['strategy', 'trades', 'wins', 'pnl'])}
<h2>By pair</h2>{table(s['by_symbol'], ['symbol', 'trades', 'pnl'])}
{inv_part}{risk_part}{ex_part}
<p class="disc">{e(DISCLAIMER)} Print this page to save it as PDF.</p></body></html>"""
