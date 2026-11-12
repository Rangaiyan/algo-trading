"""Paginated OANDA v20 candle download (doc 6.4). Needs a practice/live token."""
from __future__ import annotations

import httpx
import pandas as pd

from app.brokers.oanda import PRACTICE_URL
from app.data.pipeline import normalize

GRAN = {"M1": "M1", "M5": "M5", "M15": "M15", "M30": "M30", "H1": "H1", "H4": "H4", "D1": "D"}


def parse_candles(payload: dict) -> pd.DataFrame:
    rows = []
    for c in payload.get("candles", []):
        if not c.get("complete", True):
            continue  # never use the still-forming candle
        m = c["mid"]
        rows.append((c["time"], float(m["o"]), float(m["h"]), float(m["l"]), float(m["c"]), c["volume"]))
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"],
                            index=pd.DatetimeIndex([], tz="UTC"))
    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df.pop("time"), utc=True)
    return df


def download(token: str, instrument: str, timeframe: str, start: str, end: str,
             base_url: str = PRACTICE_URL) -> pd.DataFrame:
    headers = {"Authorization": f"Bearer {token}"}
    cursor, parts = pd.Timestamp(start, tz="UTC"), []
    end_ts = pd.Timestamp(end, tz="UTC")
    with httpx.Client(timeout=30, headers=headers) as client:
        while cursor < end_ts:
            r = client.get(f"{base_url}/v3/instruments/{instrument}/candles", params={
                "granularity": GRAN[timeframe], "price": "M", "count": 5000,
                "from": cursor.strftime("%Y-%m-%dT%H:%M:%SZ")})
            r.raise_for_status()
            df = parse_candles(r.json())
            if df.empty:
                break
            parts.append(df)
            nxt = df.index[-1] + pd.Timedelta(seconds=1)
            if nxt <= cursor:
                break
            cursor = nxt
    if not parts:
        return normalize(pd.DataFrame(columns=["open", "high", "low", "close"],
                                      index=pd.DatetimeIndex([], tz="UTC")))
    out = pd.concat(parts)
    return normalize(out[out.index < end_ts])
