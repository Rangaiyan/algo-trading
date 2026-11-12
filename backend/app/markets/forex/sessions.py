"""Forex sessions and ICT kill zones, evaluated in America/New_York with DST (doc 7.3, 8.3)."""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

# Default windows in New York local time; all configurable by strategies.
SESSIONS: dict[str, tuple[time, time]] = {
    "asia": (time(20, 0), time(0, 0)),
    "london_kz": (time(2, 0), time(5, 0)),
    "ny_am_kz": (time(7, 0), time(10, 0)),
    "silver_bullet_london": (time(3, 0), time(4, 0)),
    "silver_bullet_am": (time(10, 0), time(11, 0)),
    "silver_bullet_pm": (time(14, 0), time(15, 0)),
}


def to_ny(ts_utc: datetime) -> datetime:
    if ts_utc.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware (UTC)")
    return ts_utc.astimezone(NY)


def in_session(ts_utc: datetime, name: str) -> bool:
    start, end = SESSIONS[name]
    t = to_ny(ts_utc).time()
    if start <= end:
        return start <= t < end
    return t >= start or t < end  # window crosses midnight


def forex_market_open(ts_utc: datetime) -> bool:
    """FX trades 24h Mon-Fri: opens Sun 17:00 NY, closes Fri 17:00 NY."""
    ny = to_ny(ts_utc)
    wd, t = ny.weekday(), ny.time()  # Mon=0 .. Sun=6
    if wd == 5:  # Saturday
        return False
    if wd == 4 and t >= time(17, 0):  # Friday after close
        return False
    return not (wd == 6 and t < time(17, 0))  # Sunday before open


# Local opening hours of each centre (DST handled by zoneinfo).
_CENTRES = {
    "sydney": ("Australia/Sydney", 7, 16),
    "tokyo": ("Asia/Tokyo", 9, 18),
    "london": ("Europe/London", 8, 17),
    "newyork": ("America/New_York", 8, 17),
}


def active_sessions(ts_utc: datetime) -> list[str]:
    if not forex_market_open(ts_utc):
        return []
    out = []
    for name, (tz, start, end) in _CENTRES.items():
        local = ts_utc.astimezone(ZoneInfo(tz))
        if local.weekday() < 5 and start <= local.hour < end:
            out.append(name)
    return out


def session_label(ts_utc: datetime) -> str:
    """Single label for reports: overlap when London and New York are both open."""
    act = active_sessions(ts_utc)
    if "london" in act and "newyork" in act:
        return "london+newyork"
    for pref in ("london", "newyork", "tokyo", "sydney"):
        if pref in act:
            return pref
    return "off-hours"
