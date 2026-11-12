"""Ingest -> validate -> normalize to UTC -> resample -> store -> version hash (doc 7.3)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

COLUMNS = ["open", "high", "low", "close", "volume", "spread"]
TF_RULES = {"M1": "1min", "M5": "5min", "M15": "15min", "M30": "30min", "H1": "1h", "H4": "4h", "D1": "1D"}


@dataclass
class QualityReport:
    rows: int = 0
    duplicates: int = 0
    bad_ohlc: int = 0
    weekend_bars: int = 0
    gaps: int = 0  # gaps > 1 bar inside trading hours (excluding weekend closure)
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.duplicates or self.bad_ohlc)


def load_csv(path: str | Path, tz: str = "UTC") -> pd.DataFrame:
    """CSV with columns: time,open,high,low,close[,volume,spread]. Naive times are assumed `tz`."""
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    ts = pd.to_datetime(df.pop("time"))
    ts = ts.dt.tz_localize(tz) if ts.dt.tz is None else ts
    df.index = ts.dt.tz_convert("UTC")
    df.index.name = "ts"
    return normalize(df)


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df.index.tz is None:
        raise ValueError("index must be timezone-aware; convert to UTC at ingestion")
    df = df.copy().sort_index()
    df.index = df.index.tz_convert("UTC")
    for c in ("volume", "spread"):
        if c not in df:
            df[c] = 0.0
    return df[COLUMNS].astype(float)


def validate(df: pd.DataFrame, timeframe: str = "M15") -> QualityReport:
    rep = QualityReport(rows=len(df))
    rep.duplicates = int(df.index.duplicated().sum())
    bad = (
        (df["high"] < df[["open", "close", "low"]].max(axis=1))
        | (df["low"] > df[["open", "close", "high"]].min(axis=1))
        | (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
    )
    rep.bad_ohlc = int(bad.sum())
    # FX closes Fri 22:00 UTC .. Sun 22:00 UTC (approx); Saturday bars are always suspicious.
    rep.weekend_bars = int((df.index.day_of_week == 5).sum())
    step = pd.Timedelta(TF_RULES[timeframe])
    deltas = df.index.to_series().diff().dropna()
    # a gap = missing bars, ignoring the weekend break (> 40h)
    rep.gaps = int(((deltas > step) & (deltas < pd.Timedelta(hours=40))).sum())
    for name in ("duplicates", "bad_ohlc", "weekend_bars", "gaps"):
        if getattr(rep, name):
            rep.issues.append(f"{name}={getattr(rep, name)}")
    return rep


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df[~df.index.duplicated(keep="last")]
    bad = (
        (df["high"] < df[["open", "close", "low"]].max(axis=1))
        | (df["low"] > df[["open", "close", "high"]].min(axis=1))
        | (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
    )
    return df[~bad & (df.index.day_of_week != 5)]


def resample(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    out = df.resample(TF_RULES[timeframe], label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "spread": "mean"}
    )
    return out.dropna(subset=["open"])


def data_version(df: pd.DataFrame) -> str:
    h = hashlib.sha256(pd.util.hash_pandas_object(df, index=True).values.tobytes())
    return h.hexdigest()[:12]


def store(df: pd.DataFrame, root: str | Path, symbol: str, timeframe: str) -> Path:
    p = Path(root) / symbol / f"{timeframe}.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p)
    return p


def read_store(root: str | Path, symbol: str, timeframe: str) -> pd.DataFrame:
    return pd.read_parquet(Path(root) / symbol / f"{timeframe}.parquet")


def synthetic(
    start="2024-01-01", days=120, timeframe="M15", seed=7, start_price=1.1, vol=0.0004, drift_regime=True
) -> pd.DataFrame:
    """Deterministic random-walk OHLC with trend/range regimes. For tests, never for conclusions."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=days * 96, freq=TF_RULES[timeframe], tz="UTC")
    idx = idx[idx.day_of_week < 5]
    n = len(idx)
    regime = np.repeat(rng.choice([-1.0, 0.0, 1.0], size=n // 500 + 1), 500)[:n] if drift_regime else 0
    ret = rng.normal(0, vol, n) + regime * vol * 0.15
    close = start_price * np.exp(np.cumsum(ret))
    open_ = np.concatenate([[start_price], close[:-1]])
    wick = np.abs(rng.normal(0, vol * 0.6, (n, 2))) * close[:, None]
    high = np.maximum(open_, close) + wick[:, 0]
    low = np.minimum(open_, close) - wick[:, 1]
    return normalize(
        pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                      "volume": 100.0, "spread": 0.0001 * 0.8}, index=idx)
    )
