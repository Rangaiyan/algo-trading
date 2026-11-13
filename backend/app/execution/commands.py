"""Telegram commands (doc 14.4). Allow-listed chats only (checked by the notifier); destructive commands need a
second confirming message within 60 seconds; every command is written to the audit log; no secrets or full
account numbers are ever sent."""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

HELP = ("Commands:\n/status · /positions · /pnl · /investment · /trades [n] · /risk\n"
        "/report daily|weekly|monthly\n/pause <session-id> · /resume <session-id>\n"
        "/killswitch (asks for confirmation) · /help")


class CommandHandler:
    def __init__(self, engine, account_fn, closed_fn, investment_fn, report_fn, audit_path: str = "runtime/audit.log"):
        self.engine, self.account_fn, self.closed_fn = engine, account_fn, closed_fn
        self.investment_fn, self.report_fn = investment_fn, report_fn
        self.audit = Path(audit_path)
        self.pending_kill: dict[str, float] = {}

    def _log(self, chat: str, text: str, outcome: str) -> None:
        self.audit.parent.mkdir(parents=True, exist_ok=True)
        with self.audit.open("a") as f:
            f.write(json.dumps({"at": datetime.now(UTC).isoformat(timespec="seconds"), "chat": chat[-4:],
                                "command": text[:80], "outcome": outcome[:120]}) + "\n")

    def handle(self, chat: str, text: str) -> str:
        parts = text.strip().split()
        cmd, args = (parts[0].split("@")[0].lower(), parts[1:]) if parts else ("", [])
        try:
            reply = self._dispatch(chat, cmd, args)
        except Exception as e:  # noqa: BLE001
            reply = f"Error: {type(e).__name__}: {e}"
        self._log(chat, text, reply.splitlines()[0] if reply else "")
        return reply

    def _dispatch(self, chat: str, cmd: str, args: list[str]) -> str:
        eng = self.engine
        if cmd in ("/help", "/start"):
            return HELP
        if cmd == "/status":
            st, r = eng.state, eng.risk
            run = [s for s in eng.sessions if s["status"] == "running"]
            return (f"Rinz Algo · MT5 {'connected' if st.get('connected') else 'NOT connected'}\n"
                    f"Trading: {'HALTED (' + r.state['halt'] + ')' if r.halted else 'active'}\n"
                    f"Running sessions ({len(run)}): " + (", ".join(f"{s['name']} [{s['id']}]" for s in run) or "none")
                    + f"\nLast check: {st.get('last_tick')}")
        if cmd == "/positions":
            pos = self.engine.broker.gw.get("/positions")
            if not pos:
                return "No open positions."
            return "Open positions:\n" + "\n".join(
                f"{p['symbol']} {p['side'].upper()} {p['qty']} @ {p['entry_price']} · SL {p['stop_loss']} · "
                f"{'+' if p['unrealized_pnl'] >= 0 else ''}${p['unrealized_pnl']:,.2f}" for p in pos)
        if cmd == "/pnl":
            a = self.account_fn()
            if not a.get("connected"):
                return a.get("detail", "MT5 not connected")
            p = a.get("pnl") or {}
            f = lambda x: f"{'+' if x >= 0 else ''}${x:,.2f}"  # noqa: E731
            return (f"P&L (realised): today {f(p.get('today', 0))} · week {f(p.get('week', 0))} · month {f(p.get('month', 0))}\n"
                    f"Floating {f(a['floating'])} · Equity ${a['equity']:,.2f}")
        if cmd == "/investment":
            i = self.investment_fn()
            return (f"Invested ${i['invested']:,.2f} · Value ${i['current_value']:,.2f}\nNet {'+' if i['net_profit'] >= 0 else ''}"
                    f"${i['net_profit']:,.2f} ({i['return_pct']}%) · TWR {i['twr_pct']}% · Max DD {i['max_drawdown_pct']}%")
        if cmd == "/trades":
            n = int(args[0]) if args and args[0].isdigit() else 10
            ts = sorted(self.closed_fn(), key=lambda t: t["closed_at"], reverse=True)[:min(n, 30)]
            return "Last trades:\n" + ("\n".join(f"{t['closed_at'][:16]} {t['symbol']} {t['side']} {'+' if t['pnl'] >= 0 else ''}${t['pnl']:,.2f}"
                                                  for t in ts) or "none")
        if cmd == "/risk":
            a = self.account_fn()
            u = eng.risk.usage(a.get("equity")) if a.get("connected") else {}
            c = eng.risk.config
            return (f"Risk: {c.risk_pct}% per trade · max {c.max_open_positions} positions\n"
                    f"Today {u.get('day_pct', '—')}% (limit -{c.daily_loss_limit_pct}%) · week {u.get('week_pct', '—')}% · "
                    f"drawdown {u.get('drawdown_pct', '—')}% (limit -{c.max_drawdown_pct}%)\n"
                    f"Halt: {eng.risk.state['halt'] or 'none'}")
        if cmd == "/report":
            period = args[0] if args and args[0] in ("daily", "weekly", "monthly") else "daily"
            return self.report_fn(period)
        if cmd in ("/pause", "/resume"):
            if not args:
                return f"Usage: {cmd} <session-id>. Sessions: " + ", ".join(f"{s['id']} ({s['name']})" for s in eng.sessions)
            s = eng.set_status(args[0], "paused" if cmd == "/pause" else "running")
            return f"{s['name']} is now {s['status']}."
        if cmd == "/killswitch":
            if args and args[0].upper() == "CONFIRM" and time.time() - self.pending_kill.get(chat, 0) <= 60:
                self.pending_kill.pop(chat, None)
                r = eng.kill()
                return (f"🛑 KILL SWITCH DONE · trading halted\nClosed {len(r['closed'])} positions, cancelled {len(r['cancelled'])} orders, "
                        f"failed {len(r['failed'])}.\nResume from the dashboard when ready.")
            self.pending_kill[chat] = time.time()
            return "⚠️ This will close all Rinz positions, cancel pending orders and halt trading.\nSend /killswitch CONFIRM within 60 seconds."
        return f"Unknown command {cmd}. {HELP}"
