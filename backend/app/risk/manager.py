"""Risk manager (doc 13). Every signal passes here before an order is sent, in paper and live alike.

Halts:
  daily     - daily loss limit hit; clears automatically at the next trading day (17:00 New York)
  weekly    - weekly loss limit hit; clears at the next trading week
  drawdown  - equity fell too far below its peak; needs a manual resume
  kill      - kill switch pressed; needs a manual resume
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

RUNTIME = "runtime"
AUTO_CLEAR = {"daily", "weekly"}


@dataclass
class RiskConfig:
    risk_pct: float = 0.5                  # equity risked per trade (doc: 0.5%, 0.25% when live starts)
    max_risk_pct: float = 1.0              # hard cap, whatever the setting above says
    max_open_positions: int = 3
    max_per_symbol: int = 1
    max_usd_exposure: int = 2              # positions leaning the same way on USD
    daily_loss_limit_pct: float = 2.0
    weekly_loss_limit_pct: float = 4.0
    max_drawdown_pct: float = 10.0
    min_margin_level_pct: float = 300.0
    max_trades_per_day: int = 5            # per strategy session
    max_spread_pips: dict = field(default_factory=lambda: {"default": 2.0, "XAUUSD": 6.0, "USDJPY": 2.5})

    def spread_cap(self, symbol: str) -> float:
        return float(self.max_spread_pips.get(symbol, self.max_spread_pips.get("default", 2.0)))


@dataclass
class Decision:
    ok: bool
    reason: str = ""
    lots: float = 0.0
    risk_money: float = 0.0
    checks: list[str] = field(default_factory=list)


def trading_day(ts: datetime) -> str:
    ny = pd.Timestamp(ts).tz_convert("America/New_York")
    return str((ny + pd.Timedelta(hours=7)).date())  # FX day rolls at 17:00 New York


def trading_week(ts: datetime) -> str:
    d = pd.Timestamp(trading_day(ts))
    return str((d - pd.Timedelta(days=d.weekday())).date())


def usd_direction(symbol: str, side: str) -> int:
    """+1 = long USD, -1 = short USD, 0 = no USD leg."""
    s = 1 if side == "buy" else -1
    if symbol.startswith("USD"):
        return s
    if symbol.endswith("USD"):
        return -s
    return 0


def lot_loss_usd(symbol: str, entry: float, stop: float, contract_size: float) -> float:
    """Account-currency (USD) loss for 1.0 lot if the stop is hit."""
    move = abs(entry - stop) * contract_size
    if symbol.startswith("USD") and not symbol.endswith("USD"):
        move /= entry  # quote currency is not USD (e.g. USDJPY): convert at the current price
    return move


class RiskManager:
    def __init__(self, root: str = RUNTIME):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.cfg_path, self.state_path = self.root / "risk_config.json", self.root / "risk_state.json"
        self.config = RiskConfig(**json.loads(self.cfg_path.read_text())) if self.cfg_path.exists() else RiskConfig()
        self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {
            "halt": None, "halt_reason": "", "halted_at": None, "day": None, "day_start_equity": None,
            "week": None, "week_start_equity": None, "peak_equity": None, "events": []}

    # ---------- persistence ----------
    def save(self) -> None:
        self.cfg_path.write_text(json.dumps(asdict(self.config), indent=1))
        self.state_path.write_text(json.dumps(self.state, indent=1, default=str))

    def update_config(self, patch: dict) -> RiskConfig:
        allowed = set(asdict(self.config))
        bad = set(patch) - allowed
        if bad:
            raise ValueError(f"unknown risk settings: {sorted(bad)}")
        merged = {**asdict(self.config), **patch}
        if merged["risk_pct"] <= 0 or merged["risk_pct"] > merged["max_risk_pct"]:
            raise ValueError("risk_pct must be above 0 and not above max_risk_pct")
        if merged["max_risk_pct"] > 2.0:
            raise ValueError("max_risk_pct above 2% is not allowed")
        self.config = RiskConfig(**merged)
        self._event("config", f"risk settings changed: {sorted(patch)}")
        self.save()
        return self.config

    def _event(self, kind: str, msg: str) -> None:
        self.state["events"] = (self.state.get("events") or [])[-199:] + [
            {"at": datetime.now(UTC).isoformat(timespec="seconds"), "kind": kind, "msg": msg}]

    # ---------- halts ----------
    @property
    def halted(self) -> bool:
        return self.state.get("halt") is not None

    def halt(self, kind: str, reason: str) -> bool:
        """Returns True if this call newly halted trading."""
        if self.state.get("halt") in ("kill", "drawdown") and kind in AUTO_CLEAR:
            return False  # a stronger halt is already in force
        new = self.state.get("halt") != kind
        self.state.update(halt=kind, halt_reason=reason, halted_at=datetime.now(UTC).isoformat(timespec="seconds"))
        if new:
            self._event("halt", f"{kind}: {reason}")
        self.save()
        return new

    def resume(self, note: str = "") -> None:
        self._event("resume", f"trading resumed (was {self.state.get('halt')}) {note}".strip())
        self.state.update(halt=None, halt_reason="", halted_at=None)
        self.save()

    # ---------- equity tracking (call every loop) ----------
    def observe_equity(self, equity: float, now: datetime | None = None) -> list[str]:
        """Roll day/week, track the peak, and halt on loss limits. Returns alert messages for new halts."""
        now = now or datetime.now(UTC)
        alerts: list[str] = []
        day, week = trading_day(now), trading_week(now)
        if self.state.get("day") != day:
            self.state.update(day=day, day_start_equity=equity)
            if self.state.get("halt") == "daily":
                self.resume("(new trading day)")
        if self.state.get("week") != week:
            self.state.update(week=week, week_start_equity=equity)
            if self.state.get("halt") == "weekly":
                self.resume("(new trading week)")
        self.state["peak_equity"] = max(self.state.get("peak_equity") or equity, equity)
        c = self.config
        d0, w0, peak = self.state["day_start_equity"], self.state["week_start_equity"], self.state["peak_equity"]
        day_pct, week_pct = (equity / d0 - 1) * 100, (equity / w0 - 1) * 100
        dd_pct = (equity / peak - 1) * 100
        if dd_pct <= -c.max_drawdown_pct and self.halt("drawdown", f"equity {dd_pct:.2f}% below its peak ${peak:,.2f}"):
            alerts.append(f"🚨 RISK · MAX DRAWDOWN\nEquity is {dd_pct:.2f}% below its peak (limit {c.max_drawdown_pct}%). "
                          "All trading halted until you resume it.")
        elif week_pct <= -c.weekly_loss_limit_pct and self.halt("weekly", f"weekly loss {week_pct:.2f}%"):
            alerts.append(f"🚨 RISK · WEEKLY LOSS LIMIT\nLoss this week {week_pct:.2f}% (limit {c.weekly_loss_limit_pct}%). Halted for the week.")
        elif day_pct <= -c.daily_loss_limit_pct and self.halt("daily", f"daily loss {day_pct:.2f}%"):
            alerts.append(f"🚨 RISK · DAILY LOSS LIMIT HIT\nLoss today {day_pct:.2f}% (limit {c.daily_loss_limit_pct}%). Trading halted for today.")
        self.save()
        return alerts

    def usage(self, equity: float | None) -> dict:
        s, c = self.state, self.config
        if not equity or not s.get("day_start_equity"):
            return {}
        return {"day_pct": round((equity / s["day_start_equity"] - 1) * 100, 3),
                "week_pct": round((equity / s["week_start_equity"] - 1) * 100, 3),
                "drawdown_pct": round((equity / s["peak_equity"] - 1) * 100, 3),
                "limits": {"day": -c.daily_loss_limit_pct, "week": -c.weekly_loss_limit_pct, "drawdown": -c.max_drawdown_pct}}

    # ---------- pre-trade check ----------
    def check(self, *, symbol: str, side: str, entry: float, stop: float, account: dict, positions: list[dict],
              spec: dict, pip_size: float, trades_today: int, pending_tags: int = 0) -> Decision:
        c, checks = self.config, []
        if self.halted:
            return Decision(False, f"trading halted ({self.state['halt']}: {self.state['halt_reason']})")
        equity = float(account["equity"])
        open_n = len(positions) + pending_tags
        if open_n >= c.max_open_positions:
            return Decision(False, f"max open positions reached ({open_n}/{c.max_open_positions})")
        same = sum(p["symbol"] == symbol for p in positions)
        if same >= c.max_per_symbol:
            return Decision(False, f"already {same} position(s) on {symbol} (max {c.max_per_symbol})")
        d = usd_direction(symbol, side)
        if d:
            lean = sum(usd_direction(p["symbol"], p["side"]) == d for p in positions) + 1
            if lean > c.max_usd_exposure:
                return Decision(False, f"USD exposure: {lean} positions {'long' if d > 0 else 'short'} USD (max {c.max_usd_exposure})")
        margin, level = account.get("margin_used") or 0, None
        if margin:
            level = equity / margin * 100
            if level < c.min_margin_level_pct:
                return Decision(False, f"margin level {level:.0f}% below {c.min_margin_level_pct:.0f}%")
        spread_pips = float(spec.get("spread_points") or 0) * float(spec["point"]) / pip_size
        if spread_pips > c.spread_cap(symbol):
            return Decision(False, f"spread {spread_pips:.1f} pips above the {c.spread_cap(symbol)} pip limit")
        if trades_today >= c.max_trades_per_day:
            return Decision(False, f"{trades_today} trades today for this strategy (max {c.max_trades_per_day})")
        if (side == "buy" and stop >= entry) or (side == "sell" and stop <= entry):
            return Decision(False, "stop-loss on the wrong side of the entry")
        risk_money = equity * min(c.risk_pct, c.max_risk_pct) / 100
        per_lot = lot_loss_usd(symbol, entry, stop, float(spec["contract_size"]))
        step, vmin, vmax = float(spec.get("volume_step") or 0.01), float(spec.get("volume_min") or 0.01), float(spec.get("volume_max") or 50)
        lots = min(math.floor(risk_money / per_lot / step + 1e-9) * step, vmax) if per_lot > 0 else 0
        if lots < vmin:
            return Decision(False, f"stop too wide for the risk budget: {vmin} lot would risk ${per_lot * vmin:,.2f} > ${risk_money:,.2f}")
        checks += [f"risk ${risk_money:,.2f} ({min(c.risk_pct, c.max_risk_pct)}%)", f"spread {spread_pips:.1f} pips",
                   f"{open_n + 1}/{c.max_open_positions} positions"] + ([f"margin level {level:.0f}%"] if level else [])
        return Decision(True, "accepted", round(lots, 2), round(per_lot * round(lots, 2), 2), checks)
