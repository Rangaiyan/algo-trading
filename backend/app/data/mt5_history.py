"""Download real candle history from the broker (MT5 via the gateway) into the data store (doc 7).

Pipeline per symbol/timeframe: fetch in chunks -> convert to UTC frame (spread points -> price)
-> merge with what is already stored -> clean -> validate -> store Parquet + meta JSON
(quality report, data version hash, hold-out start, symbol spec for the cost model).

Each timeframe is downloaded natively from MT5 rather than resampled from M1, because MT5 caps
history per timeframe at the terminal's "Max bars in chart" setting: native M15/H1 reach years
further back than M1 does.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd

from app.core.config import get_settings
from app.data import pipeline as P

SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD"]
TIMEFRAMES = ["M1", "M5", "M15", "H1", "H4", "D1"]
HOLDOUT_MONTHS = 6  # doc 7.2: most recent block is never used for tuning
BAR_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}
CHUNK_BARS = 20_000  # bars per gateway request (keeps each JSON response a few MB)


class GatewayError(RuntimeError):
    pass


class Gateway:
    """Thin client for the MT5 gateway's read-only endpoints."""

    def __init__(self, url: str | None = None, token: str | None = None, timeout: float = 120):
        s = get_settings()
        url = url or s.mt5_gateway_url
        if not url:
            raise GatewayError("MT5_GATEWAY_URL is not set")
        self.base = url.rstrip("/")
        self.client = httpx.Client(timeout=timeout, headers={"Authorization": f"Bearer {token or s.mt5_gateway_token}"})

    def get(self, path: str, **params):
        try:
            r = self.client.get(f"{self.base}{path}", params=params)
        except httpx.HTTPError as e:
            raise GatewayError(f"MT5 gateway not reachable: {e}") from e
        if r.status_code != 200:
            raise GatewayError(f"gateway {path} -> {r.status_code}: {r.text[:200]}")
        return r.json()

    def send(self, method: str, path: str, body: dict | None = None):
        """POST/DELETE. Broker-side rejections come back as a dict with ok=False; HTTP errors raise."""
        try:
            r = self.client.request(method, f"{self.base}{path}", json=body)
        except httpx.HTTPError as e:
            raise GatewayError(f"MT5 gateway not reachable: {e}") from e
        if r.status_code != 200:
            detail = r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json") else r.text
            raise GatewayError(f"{detail or r.status_code}")
        return r.json()

    def candles(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[dict]:
        return self.get("/candles", symbol=symbol, timeframe=timeframe, start=start.isoformat(), end=end.isoformat())

    def symbol(self, symbol: str) -> dict:
        return self.get(f"/symbols/{symbol}")

    def status(self) -> dict:
        return self.get("/status")


def to_frame(rows: list[dict], point: float) -> pd.DataFrame:
    """Gateway candle rows -> normalized UTC frame. MT5 spread is in points; the engine wants price units."""
    if not rows:
        return pd.DataFrame(columns=P.COLUMNS, index=pd.DatetimeIndex([], tz="UTC", name="ts"))
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df.pop("ts"), utc=True)
    df.index.name = "ts"
    df["spread"] = df["spread"].astype(float) * point
    return P.normalize(df)


def _paths(root: str | Path, symbol: str, timeframe: str) -> tuple[Path, Path]:
    d = Path(root) / symbol
    return d / f"{timeframe}.parquet", d / f"{timeframe}.meta.json"


def read_meta(root: str | Path, symbol: str, timeframe: str) -> dict | None:
    meta = _paths(root, symbol, timeframe)[1]
    return json.loads(meta.read_text()) if meta.exists() else None


def download(gw: Gateway, root: str | Path, symbol: str, timeframe: str, years: float = 5,
             now: datetime | None = None, log: Callable[[str], None] = print) -> dict:
    """Fetch history (incrementally if some is stored), clean, validate and store. Returns the meta dict."""
    now = now or datetime.now(UTC)
    spec = gw.symbol(symbol)
    point = float(spec["point"])
    data_path, meta_path = _paths(root, symbol, timeframe)
    have = P.read_store(root, symbol, timeframe) if data_path.exists() else None

    want_start = now - timedelta(days=round(365.25 * years))
    # Re-fetch the last stored day too, so a bar that was still forming at the last run gets finalized.
    start = want_start if have is None or have.empty or have.index[0] > want_start + timedelta(days=7) \
        else have.index[-1].to_pydatetime() - timedelta(days=1)
    step = timedelta(minutes=BAR_MINUTES[timeframe] * CHUNK_BARS)

    frames, t = [], start
    while t < now:
        t_end = min(t + step, now)
        rows = gw.candles(symbol, timeframe, t, t_end)
        if rows:
            frames.append(to_frame(rows, point))
        t = t_end
    new = pd.concat(frames) if frames else to_frame([], point)
    log(f"  {symbol} {timeframe}: fetched {len(new):,} bars from {start:%Y-%m-%d}")

    df = new if have is None else pd.concat([have, new])
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]  # newer fetch wins
    df = df[df.index < pd.Timestamp(now) - pd.Timedelta(minutes=BAR_MINUTES[timeframe])]  # drop the still-forming bar
    report = P.validate(df, timeframe)
    df = P.clean(df)
    if df.empty:
        raise GatewayError(f"no {timeframe} history returned for {symbol}")
    P.store(df, root, symbol, timeframe)

    first, last = df.index[0], df.index[-1]
    meta = {
        "symbol": symbol, "timeframe": timeframe, "source": "mt5",
        "bars": len(df), "start": first.isoformat(), "end": last.isoformat(),
        "years": round((last - first).days / 365.25, 2),
        "holdout_start": (last - pd.DateOffset(months=HOLDOUT_MONTHS)).isoformat(),
        "data_version": P.data_version(df),
        "quality": {**asdict(report), "ok": report.ok, "cleaned_rows": report.rows - len(df)},
        "spec": spec,
        "updated_at": now.isoformat(),
    }
    meta_path.write_text(json.dumps(meta, indent=1, default=str))
    return meta


def download_all(root: str | Path, symbols: list[str] | None = None, timeframes: list[str] | None = None,
                 years: float = 5, log: Callable[[str], None] = print) -> list[dict]:
    gw = Gateway()
    st = gw.status()
    log(f"MT5 {st.get('server')} ({st.get('account_mode')}), max bars per timeframe: {st.get('max_bars')}")
    out = []
    for sym in symbols or SYMBOLS:
        for tf in timeframes or TIMEFRAMES:
            try:
                out.append(download(gw, root, sym, tf, years, log=log))
            except GatewayError as e:
                log(f"  {sym} {tf}: FAILED {e}")
                out.append({"symbol": sym, "timeframe": tf, "error": str(e)})
    return out


def catalog(root: str | Path) -> list[dict]:
    """What is stored, with range, size and quality (meta files only; cheap)."""
    out = []
    for meta in sorted(Path(root).glob("*/*.meta.json")):
        m = json.loads(meta.read_text())
        m.pop("spec", None)
        out.append(m)
    return out
