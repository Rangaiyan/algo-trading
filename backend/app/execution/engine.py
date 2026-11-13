"""Trading engine (doc 11, 13): runs strategy sessions on live MT5 candles and sends orders through the risk manager.

One `tick()` = one pass: read the account -> risk bookkeeping -> reconcile our order records with MT5 ->
for every running session with a newly CLOSED candle, run the strategy and act on a signal at that candle.
State lives in runtime/ (sessions, order records, equity snapshots) so a restart picks up where it left off;
stop-losses are always broker-side, so open trades stay protected while the backend is down.
"""
from __future__ import annotations

import functools
import hashlib
import json
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from app.backtest.engine import Context
from app.backtest.runner import STRATEGIES, instrument
from app.data.mt5_history import BAR_MINUTES, to_frame
from app.domain import Bar, Order, OrderType, Side
from app.execution.magic import STRATEGY_MAGIC, strategy_of
from app.risk.manager import RUNTIME, RiskManager, trading_day

WINDOW_BARS = 800            # candles fed to a strategy each time (warm-up for EMAs / structure)
SNAPSHOT_EVERY = timedelta(minutes=5)
OPEN_STATES = {"pending", "open"}


def locked(fn):
    """Engine state is shared by the background loop and the API: one change at a time."""
    @functools.wraps(fn)
    def wrap(self, *a, **kw):
        with self.lock:
            return fn(self, *a, **kw)
    return wrap


def tag_for(client_id: str) -> str:
    """Must match the gateway's _tag(): what MT5 stores in the order/position comment."""
    return "rz:" + hashlib.sha1(client_id.encode()).hexdigest()[:16]


def magic_for(strategy: str, session_id: str) -> int:
    if strategy in STRATEGY_MAGIC:
        return STRATEGY_MAGIC[strategy]
    return 4500 + int(hashlib.sha1(session_id.encode()).hexdigest(), 16) % 400  # rule/generated strategies: SMC desk


class TradingEngine:
    def __init__(self, broker, root: str = RUNTIME, now: Callable[[], datetime] | None = None):
        self.broker = broker           # MT5Broker (or a fake in tests); broker.gw = gateway client
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.risk = RiskManager(root)
        self.now = now or (lambda: datetime.now(UTC))
        self.sessions: list[dict] = self._load("sessions.json", [])
        self.orders: list[dict] = self._load("orders.json", [])
        self.state: dict = self._load("engine.json", {"last_tick": None, "last_error": None, "issues": [],
                                                       "last_snapshot": None, "day": None, "connected": None})
        self._specs: dict[str, dict] = {}
        self.lock = threading.RLock()

    # ---------------- persistence ----------------
    def _load(self, name: str, default):
        p = self.root / name
        return json.loads(p.read_text()) if p.exists() else default

    def _save(self) -> None:
        for name, obj in (("sessions.json", self.sessions), ("orders.json", self.orders[-5000:]), ("engine.json", self.state)):
            (self.root / name).write_text(json.dumps(obj, indent=1, default=str))

    # ---------------- sessions ----------------
    @locked
    def add_session(self, strategy: str, symbol: str, timeframe: str, params: dict | None = None, name: str = "",
                    mode: str = "paper", library_id: str | None = None) -> dict:
        if strategy not in STRATEGIES:
            raise ValueError(f"unknown strategy {strategy}")
        if timeframe not in BAR_MINUTES:
            raise ValueError(f"unknown timeframe {timeframe}")
        instrument(symbol)  # raises StopIteration for unknown symbols
        STRATEGIES[strategy](**(params or {}))  # fail fast on bad params / rule specs
        sid = uuid.uuid4().hex[:8]
        s = {"id": sid, "name": name or f"{strategy} {symbol} {timeframe}", "strategy": strategy, "symbol": symbol,
             "timeframe": timeframe, "params": params or {}, "mode": mode, "library_id": library_id,
             "magic": magic_for(strategy, sid), "status": "paused", "created_at": self.now().isoformat(timespec="seconds"),
             "last_bar": None, "last_signal": None, "last_error": None}
        self.sessions.append(s)
        self._save()
        return s

    @locked
    def set_status(self, sid: str, status: str) -> dict:
        if status not in ("running", "paused", "stopped"):
            raise ValueError("status must be running, paused or stopped")
        s = self.session(sid)
        if status == "running" and self.risk.halted and self.risk.state["halt"] in ("kill", "drawdown"):
            raise ValueError(f"trading is halted ({self.risk.state['halt']}); resume trading first")
        s["status"] = status
        if status == "running":
            s["last_bar"] = None  # only act on candles that close from now on (see _run_session)
            s["started_at"] = self.now().isoformat(timespec="seconds")
        self._save()
        return s

    @locked
    def remove_session(self, sid: str) -> None:
        if any(o["session_id"] == sid and o["state"] in OPEN_STATES for o in self.orders):
            raise ValueError("this session still has an open trade or pending order; close it first")
        self.sessions = [s for s in self.sessions if s["id"] != sid]
        self._save()

    def session(self, sid: str) -> dict:
        s = next((x for x in self.sessions if x["id"] == sid), None)
        if s is None:
            raise KeyError(sid)
        return s

    # ---------------- helpers ----------------
    def spec(self, symbol: str, fresh: bool = False) -> dict:
        if fresh or symbol not in self._specs:
            self._specs[symbol] = self.broker.gw.symbol(symbol)
        return self._specs[symbol]

    def _closed_candles(self, symbol: str, tf: str) -> pd.DataFrame:
        now = self.now()
        mins = BAR_MINUTES[tf]
        start = now - timedelta(minutes=mins * WINDOW_BARS * 1.6 + 3 * 1440)  # weekends
        df = to_frame(self.broker.gw.candles(symbol, tf, start, now), float(self.spec(symbol)["point"]))
        return df[df.index + pd.Timedelta(minutes=mins) <= pd.Timestamp(now)].iloc[-WINDOW_BARS:]  # drop the forming bar

    @staticmethod
    def _signal_on_last_bar(strategy, inst, df: pd.DataFrame):
        ctx = Context(df, inst)
        strategy.on_start(ctx)
        o, h, lo, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
        stamps = df.index.to_pydatetime()
        sigs = []
        for i in range(len(df)):
            ctx.i = i
            sigs = strategy.on_bar(ctx, Bar(stamps[i], o[i], h[i], lo[i], c[i]))
        return sigs

    def _issue(self, key: str, msg: str, alerts: list) -> None:
        if key not in {i["key"] for i in self.state["issues"]}:
            self.state["issues"] = self.state["issues"][-49:] + [{"key": key, "msg": msg, "at": self.now().isoformat(timespec="seconds")}]
            alerts.append((f"⚠️ RECONCILIATION\n{msg}", "warning"))

    # ---------------- reconciliation ----------------
    def reconcile(self, positions: list[dict], pending: list[dict], alerts: list) -> None:
        pos_by_tag = {p.get("tag"): p for p in positions if p.get("tag")}
        pend_tags = {o.get("tag") for o in pending}
        known = {o["tag"] for o in self.orders}
        for rec in self.orders:
            if rec["state"] not in OPEN_STATES:
                continue
            p = pos_by_tag.get(rec["tag"])
            if rec["state"] == "pending":
                if p:
                    self._mark_open(rec, p, alerts)
                elif rec["tag"] not in pend_tags:
                    self._settle_from_history(rec, alerts, was_pending=True)
            elif rec["state"] == "open" and not p:
                self._settle_from_history(rec, alerts)
        for p in positions:
            t = p.get("tag") or ""
            if t.startswith("rz:") and t not in known:
                self._issue(f"unknown:{p['id']}", f"MT5 has a Rinz-tagged position {p['id']} ({p['symbol']} {p['side']}) "
                                                  "that the engine has no record of.", alerts)

    def _mark_open(self, rec: dict, p: dict, alerts: list) -> None:
        pip = instrument(rec["symbol"]).pip_size
        d = 1 if rec["side"] == "buy" else -1
        rec.update(state="open", ticket=str(p["id"]), fill_price=p["entry_price"], filled_at=p.get("opened_at"),
                   slippage_pips=round((p["entry_price"] - rec["requested_price"]) * d / pip, 2))
        alerts.append((f"🟢 TRADE OPENED · {rec['mode'].upper()}\n{rec['symbol']} {rec['side'].upper()} {rec['lots']} lot @ {p['entry_price']}\n"
                       f"SL {rec['stop_loss']} · TP {rec['take_profit']} · Risk ${rec['risk_money']}\nStrategy: {rec['strategy']} ({rec['session_name']})", "info"))

    def _settle_from_history(self, rec: dict, alerts: list, was_pending: bool = False) -> None:
        start = pd.Timestamp(rec["placed_at"]) - pd.Timedelta(days=1)
        deals = [d for d in self.broker.gw.get("/deals", start=start.isoformat()) if d.get("comment") == rec["tag"]
                 or (rec.get("ticket") and str(d.get("position_id")) == rec["ticket"])]
        entry = next((d for d in deals if d["entry"] == "in"), None)
        exits = [d for d in deals if d["entry"] in ("out", "inout", "out_by")]
        if was_pending and entry is None:
            rec.update(state="expired", closed_at=self.now().isoformat(timespec="seconds"),
                       reason="limit order expired or was cancelled without filling")
            return
        if entry and not rec.get("fill_price"):
            pip = instrument(rec["symbol"]).pip_size
            d = 1 if rec["side"] == "buy" else -1
            rec.update(ticket=str(entry["position_id"]), fill_price=entry["price"], filled_at=entry["ts"],
                       slippage_pips=round((entry["price"] - rec["requested_price"]) * d / pip, 2))
        if not exits:
            pos_ids = {str(d.get("position_id")) for d in deals}
            self._issue(f"missing:{rec['tag']}", f"{rec['symbol']} trade {rec.get('ticket') or rec['tag']} is no longer open "
                                                 f"but no closing deal was found yet ({len(pos_ids)} related deals).", alerts)
            return
        last = max(exits, key=lambda d: d["ts"])
        pnl = round(sum(d["profit"] + d["commission"] + d["swap"] + d["fee"] for d in deals), 2)
        pip = instrument(rec["symbol"]).pip_size
        near = lambda a, b: b is not None and abs(a - b) <= 3 * pip  # noqa: E731
        reason = "tp" if near(last["price"], rec.get("take_profit")) else "sl" if near(last["price"], rec.get("stop_loss")) else "closed"
        rec.update(state="closed", exit_price=last["price"], closed_at=last["ts"], pnl=pnl, exit_reason=reason)
        emoji = "✅" if pnl >= 0 else "🔻"
        alerts.append((f"{emoji} TRADE CLOSED · {rec['mode'].upper()}\n{rec['symbol']} {rec['side'].upper()} {rec['lots']} lot · "
                       f"{'+' if pnl >= 0 else ''}${pnl:,.2f}\nEntry {rec.get('fill_price')} → Exit {last['price']} ({reason.upper()})\n"
                       f"Strategy: {rec['strategy']} ({rec['session_name']})", "info"))

    # ---------------- one session ----------------
    def _run_session(self, s: dict, account: dict, positions: list[dict], alerts: list) -> None:
        df = self._closed_candles(s["symbol"], s["timeframe"])
        if len(df) < 100:
            s["last_error"] = f"only {len(df)} closed candles available"
            return
        last_ts = df.index[-1].isoformat()
        if s["last_bar"] is None:      # just started: remember the latest candle, act from the next one
            s["last_bar"] = last_ts
            return
        if last_ts <= s["last_bar"]:
            return                     # no new closed candle yet
        s["last_bar"] = last_ts
        bar_age = self.now() - df.index[-1].to_pydatetime()
        if bar_age > timedelta(minutes=3 * BAR_MINUTES[s["timeframe"]]):
            s["last_error"] = f"latest candle is {bar_age} old (market closed or feed stale); not trading on it"
            return
        inst = instrument(s["symbol"])
        sigs = self._signal_on_last_bar(STRATEGIES[s["strategy"]](**s["params"]), inst, df)
        s["last_error"] = None
        if not sigs:
            return
        sig = sigs[0]
        side = "buy" if sig.side == Side.BUY else "sell"
        s["last_signal"] = {"bar": last_ts, "side": side, "entry": sig.entry, "sl": sig.stop_loss, "tp": sig.take_profit,
                            "reason": sig.reason}
        if any(o["session_id"] == s["id"] and o["state"] in OPEN_STATES for o in self.orders):
            s["last_signal"]["decision"] = "skipped: this session already has an open trade or pending order"
            return
        client_id = f"{s['id']}:{last_ts}"
        if any(o["client_id"] == client_id for o in self.orders):
            return                     # already acted on this candle (restart safety)
        spec = self.spec(s["symbol"], fresh=True)   # fresh = current spread
        ticks = self.broker.gw.get("/ticks", symbols=s["symbol"]).get(s["symbol"]) or {}
        market = ticks.get("ask") if side == "buy" else ticks.get("bid")
        if not market:
            s["last_signal"]["decision"] = "skipped: no live price"
            return
        # limit order unless price is already at/through the limit (then take the better market price)
        otype, price = OrderType.MARKET, None
        if sig.entry is not None and ((side == "buy" and market > sig.entry) or (side == "sell" and market < sig.entry)):
            otype, price = OrderType.LIMIT, float(sig.entry)
        ref = price if price is not None else market
        trades_today = sum(o["session_id"] == s["id"] and trading_day(pd.Timestamp(o["placed_at"])) == trading_day(self.now())
                           and o["state"] != "rejected" for o in self.orders)
        pend = sum(o["state"] == "pending" for o in self.orders)
        dec = self.risk.check(symbol=s["symbol"], side=side, entry=ref, stop=sig.stop_loss, account=account,
                              positions=positions, spec=spec, pip_size=inst.pip_size, trades_today=trades_today, pending_tags=pend)
        s["last_signal"]["decision"] = dec.reason
        if not dec.ok:
            alerts.append((f"⛔ SIGNAL REJECTED BY RISK\n{s['name']}: {side.upper()} {s['symbol']} — {dec.reason}", "info"))
            return
        rec = {"tag": tag_for(client_id), "client_id": client_id, "session_id": s["id"], "session_name": s["name"],
               "strategy": s["strategy"], "symbol": s["symbol"], "side": side, "type": otype.value, "lots": dec.lots,
               "requested_price": ref, "stop_loss": sig.stop_loss, "take_profit": sig.take_profit, "magic": s["magic"],
               "risk_money": dec.risk_money, "mode": s["mode"], "placed_at": self.now().isoformat(timespec="seconds"),
               "signal_bar": last_ts, "reason_signal": sig.reason,
               "spread_pips": round(float(spec.get("spread_points") or 0) * float(spec["point"]) / inst.pip_size, 2)}
        res = self.broker.place_order(
            Order(client_id, s["symbol"], Side(side), otype, dec.lots, sig.stop_loss, sig.take_profit, price),
            magic=s["magic"],
            expire_minutes=sig.expires_bars * BAR_MINUTES[s["timeframe"]] if otype == OrderType.LIMIT else None)
        raw = getattr(self.broker, "last_result", None) or {}
        rec.update(retcode=raw.get("retcode"), latency_ms=raw.get("latency_ms"), broker_ticket=res.broker_order_id)
        if not res.ok:
            rec.update(state="rejected", reason=res.reason)
            self.orders.append(rec)
            alerts.append((f"⚠️ ORDER REJECTED\n{s['name']}: {side.upper()} {dec.lots} {s['symbol']} — {res.reason}", "warning"))
            return
        rec["state"] = "pending"   # the next reconcile marks it open once MT5 shows the position
        self.orders.append(rec)
        if otype == OrderType.LIMIT:
            alerts.append((f"🕒 LIMIT ORDER PLACED · {s['mode'].upper()}\n{s['symbol']} {side.upper()} {dec.lots} lot @ {price}\n"
                           f"SL {sig.stop_loss} · TP {sig.take_profit} · expires in {sig.expires_bars} bars\nStrategy: {s['strategy']} ({s['name']})", "info"))

    # ---------------- the loop body ----------------
    @locked
    def tick(self) -> list[tuple[str, str]]:
        """One pass. Returns (message, severity) alerts for Telegram."""
        alerts: list[tuple[str, str]] = []
        now = self.now()
        self.state["last_tick"] = now.isoformat(timespec="seconds")
        try:
            st = self.broker.gw.status()
            if not st.get("terminal_connected"):
                if self.state.get("connected") is not False:
                    alerts.append(("⚠️ SYSTEM · MT5 DISCONNECTED\nThe terminal is not connected to the broker. Trading paused until it reconnects.", "critical"))
                self.state["connected"] = False
                return alerts
            if self.state.get("connected") is False:
                alerts.append(("✅ SYSTEM · MT5 RECONNECTED", "warning"))
            self.state["connected"] = True
            account = self.broker.gw.get("/account")
            positions = self.broker.gw.get("/positions")
            pending = self.broker.gw.get("/orders")
            for msg in self.risk.observe_equity(float(account["equity"]), now):
                alerts.append((msg, "critical"))
            self.reconcile(positions, pending, alerts)
            day = trading_day(now)
            if self.state.get("day") and self.state["day"] != day:
                alerts.append((self.daily_summary(self.state["day"], account), "info"))
            self.state["day"] = day
            last = self.state.get("last_snapshot")
            if not last or now - pd.Timestamp(last).to_pydatetime() >= SNAPSHOT_EVERY:
                self._snapshot(now, account, positions)
            for s in self.sessions:
                if s["status"] != "running":
                    continue
                try:
                    self._run_session(s, account, positions, alerts)
                except Exception as e:  # noqa: BLE001 - one bad session must not stop the others
                    s["last_error"] = f"{type(e).__name__}: {e}"
            self.state["last_error"] = None
        except Exception as e:  # noqa: BLE001
            msg = f"{type(e).__name__}: {e}"
            if self.state.get("last_error") != msg:
                alerts.append((f"⚠️ SYSTEM · ENGINE ERROR\n{msg}", "warning"))
            self.state["last_error"] = msg
        finally:
            self._save()
        return alerts

    def _snapshot(self, now: datetime, account: dict, positions: list[dict]) -> None:
        p = self.root / "equity.csv"
        new = not p.exists()
        with p.open("a") as f:
            if new:
                f.write("ts,balance,equity,margin_used,floating,open_positions\n")
            floating = sum(x.get("unrealized_pnl") or 0 for x in positions)
            f.write(f"{now.isoformat(timespec='seconds')},{account['balance']},{account['equity']},"
                    f"{account.get('margin_used') or 0},{round(floating, 2)},{len(positions)}\n")
        self.state["last_snapshot"] = now.isoformat(timespec="seconds")

    # ---------------- kill switch ----------------
    @locked
    def kill(self, include_manual: bool = False) -> dict:
        """Halt, pause every session, cancel pending orders and flatten positions (Rinz-placed only, unless include_manual)."""
        self.risk.halt("kill", "kill switch pressed")
        for s in self.sessions:
            if s["status"] == "running":
                s["status"] = "paused"
        ours = lambda x: include_manual or (x.get("magic") or 0) != 0 or (x.get("tag") or "").startswith("rz:")  # noqa: E731
        done = {"cancelled": [], "closed": [], "failed": []}
        for o in self.broker.gw.get("/orders"):
            if ours(o):
                r = self.broker.cancel_order(str(o["ticket"]))
                (done["cancelled"] if r.ok else done["failed"]).append({"ticket": o["ticket"], "reason": r.reason})
        for p in self.broker.gw.get("/positions"):
            if ours(p):
                r = self.broker.close_position(str(p["id"]))
                (done["closed"] if r.ok else done["failed"]).append({"ticket": p["id"], "symbol": p["symbol"], "reason": r.reason})
        self.risk._event("kill", f"kill switch: closed {len(done['closed'])}, cancelled {len(done['cancelled'])}, failed {len(done['failed'])}")
        self.risk.save()
        self._save()
        return done

    # ---------------- reporting helpers ----------------
    def daily_summary(self, day: str, account: dict) -> str:
        closed = [o for o in self.orders if o["state"] == "closed" and o.get("closed_at")
                  and trading_day(pd.Timestamp(o["closed_at"])) == day]
        pnl = sum(o.get("pnl") or 0 for o in closed)
        wins = sum((o.get("pnl") or 0) > 0 for o in closed)
        return (f"📊 DAILY SUMMARY · {day}\nTrades closed: {len(closed)} ({wins} won)\nP&L: {'+' if pnl >= 0 else ''}${pnl:,.2f}\n"
                f"Equity: ${float(account['equity']):,.2f} · open positions: {account.get('open', '—')}\n"
                f"Running sessions: {sum(s['status'] == 'running' for s in self.sessions)}"
                + (f"\nHALTED: {self.risk.state['halt']}" if self.risk.halted else ""))

    def execution_quality(self) -> dict:
        filled = [o for o in self.orders if o.get("fill_price") is not None]
        sl = [o["slippage_pips"] for o in filled if o.get("slippage_pips") is not None]
        sp = [o["spread_pips"] for o in self.orders if o.get("spread_pips") is not None]
        lat = [o["latency_ms"] for o in self.orders if o.get("latency_ms")]
        sent = [o for o in self.orders if o["state"] != "rejected" or o.get("retcode")]
        return {"orders": len(self.orders), "filled": len(filled),
                "rejected": sum(o["state"] == "rejected" for o in self.orders),
                "avg_slippage_pips": round(float(np.mean(sl)), 2) if sl else None,
                "avg_spread_pips": round(float(np.mean(sp)), 2) if sp else None,
                "avg_latency_ms": round(float(np.mean(lat)), 1) if lat else None,
                "rejection_rate": round(sum(o["state"] == "rejected" for o in self.orders) / len(sent), 3) if sent else None}

    @locked
    def status(self) -> dict:
        return {"state": self.state, "risk": {"config": self.risk.config.__dict__, "state": self.risk.state},
                "sessions": self.sessions, "orders": self.orders[-100:][::-1], "execution": self.execution_quality(),
                "strategy_names": {s["id"]: strategy_of(s["magic"]) for s in self.sessions}}
