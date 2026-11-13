"""Live MT5 connection check, used by /status for the top-bar indicator.

Asks the MT5 gateway two things: is the terminal connected to the broker server (/health),
and does our token work with an account logged in (/account). Results are cached briefly
so the frontend's polling doesn't hit the gateway on every request.
"""
from __future__ import annotations

import threading
import time

import httpx

from app.core.config import get_settings

_TTL = 10.0  # seconds
_cache: dict = {"at": 0.0, "value": None}
_lock = threading.Lock()


def _probe() -> dict:
    s = get_settings()
    if not s.mt5_gateway_url:
        return {"connected": False, "detail": "MT5_GATEWAY_URL is not set"}
    base = s.mt5_gateway_url.rstrip("/")
    try:
        with httpx.Client(timeout=2.5) as client:
            health = client.get(f"{base}/health").json()
            if not health.get("terminal_connected"):
                return {"connected": False, "detail": "Gateway running, but the MT5 terminal is not connected to the broker"}
            r = client.get(f"{base}/account", headers={"Authorization": f"Bearer {s.mt5_gateway_token}"})
    except httpx.HTTPError:
        return {"connected": False, "detail": "MT5 gateway not reachable (is mt5-gateway/start.ps1 running?)"}
    except ValueError:
        return {"connected": False, "detail": "MT5 gateway returned an invalid response"}
    if r.status_code == 401:
        return {"connected": False, "detail": "Gateway rejected the token (MT5_GATEWAY_TOKEN mismatch)"}
    if r.status_code != 200:
        return {"connected": False, "detail": f"Gateway error {r.status_code}: {r.text[:120]}"}
    acc = r.json()
    return {"connected": True, "detail": f"{acc.get('server')} · {str(acc.get('mode', '')).upper()}",
            "account_mode": acc.get("mode"), "server": acc.get("server")}


def mt5_connection() -> dict:
    with _lock:
        if _cache["value"] is not None and time.monotonic() - _cache["at"] < _TTL:
            return _cache["value"]
        value = _probe()
        _cache.update(at=time.monotonic(), value=value)
        return value
