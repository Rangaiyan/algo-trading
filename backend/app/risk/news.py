"""News filter (doc 13, 11.4 drill 7): no new entries around high-impact economic events on a pair's currencies.

Source: the public ForexFactory weekly calendar feed (no account or personal data is sent). Fetched at most once an
hour and cached in runtime/calendar.json; if a fetch fails the last copy is used and flagged as stale.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd

FEED = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
REFRESH = timedelta(hours=1)


def currencies(symbol: str) -> set[str]:
    """Currencies whose news moves this pair. Gold (XAU) is driven by USD news."""
    base, quote = symbol[:3], symbol[3:6]
    out = {base, quote} - {"XAU", "XAG"}
    if base in ("XAU", "XAG"):
        out.add("USD")
    return out


class NewsCalendar:
    def __init__(self, root: str = "runtime", fetch=None):
        self.path = Path(root) / "calendar.json"
        self.fetch = fetch or self._fetch
        cached = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.events: list[dict] = cached.get("events", [])
        self.fetched_at: str | None = cached.get("fetched_at")   # last successful fetch
        self.tried_at: str | None = self.fetched_at              # last attempt (success or not)
        self.error: str | None = None

    @staticmethod
    def _fetch() -> list[dict]:
        r = httpx.get(FEED, timeout=20, headers={"User-Agent": "Mozilla/5.0 (compatible; calendar-client)"})
        r.raise_for_status()
        return r.json()

    def refresh(self, now: datetime, force: bool = False) -> None:
        if not force and self.tried_at and now - pd.Timestamp(self.tried_at).to_pydatetime() < REFRESH:
            return  # at most one attempt per hour (the feed rate-limits aggressive clients)
        self.tried_at = now.isoformat(timespec="seconds")
        try:
            raw = self.fetch()
            self.events = [{"title": e["title"], "currency": e["country"], "impact": e["impact"],
                            "at": pd.Timestamp(e["date"]).tz_convert("UTC").isoformat(),
                            "forecast": e.get("forecast"), "previous": e.get("previous")}
                           for e in raw if e.get("date")]
            self.fetched_at, self.error = now.isoformat(timespec="seconds"), None
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"fetched_at": self.fetched_at, "events": self.events}, indent=1))
        except Exception as e:  # noqa: BLE001 - keep the last good calendar
            self.error = f"{type(e).__name__}: {str(e).splitlines()[0][:160]}"

    def stale(self, now: datetime) -> bool:
        """No successful fetch in the last 12 hours (or ever): the filter may be blind."""
        return self.fetched_at is None or now - pd.Timestamp(self.fetched_at).to_pydatetime() > timedelta(hours=12)

    def _relevant(self, symbol: str, impacts: list[str]) -> list[dict]:
        cur = currencies(symbol)
        return [e for e in self.events if e["currency"] in cur and e["impact"] in impacts]

    def blackout(self, symbol: str, now: datetime, before_min: int, after_min: int, impacts: list[str]) -> dict | None:
        """The event that blocks a new entry on `symbol` right now, if any."""
        for e in self._relevant(symbol, impacts):
            at = pd.Timestamp(e["at"]).to_pydatetime()
            if at - timedelta(minutes=before_min) <= now <= at + timedelta(minutes=after_min):
                return e
        return None

    def upcoming(self, symbols: list[str], now: datetime, within_min: int, impacts: list[str]) -> list[dict]:
        seen, out = set(), []
        for s in symbols:
            for e in self._relevant(s, impacts):
                at = pd.Timestamp(e["at"]).to_pydatetime()
                k = f"{e['currency']}|{e['title']}|{e['at']}"
                if now <= at <= now + timedelta(minutes=within_min) and k not in seen:
                    seen.add(k)
                    out.append(e | {"key": k})
        return sorted(out, key=lambda e: e["at"])

    def week(self, impacts: list[str] | None = None) -> list[dict]:
        return sorted([e for e in self.events if not impacts or e["impact"] in impacts], key=lambda e: e["at"])


def now_utc() -> datetime:
    return datetime.now(UTC)
