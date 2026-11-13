"""Access control for the dashboard API.

Off by default (the backend only listens on this PC). Set APP_ACCESS_TOKEN in .env before making the backend
reachable from other devices (phone / LAN / Tailscale): every request then needs `Authorization: Bearer <token>`
(or `?access_token=` for plain download links). /health stays open for uptime monitors.
"""
from __future__ import annotations

import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

OPEN_PATHS = {"/health"}
# this PC, private networks (home Wi-Fi) and Tailscale names; any port (Vite dev 5173 / preview 4173 / Tailscale 443)
ORIGIN_REGEX = (r"^https?://(localhost|127\.0\.0\.1|\[::1\]|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
                r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|100\.\d{1,3}\.\d{1,3}\.\d{1,3}|[a-z0-9-]+(\.[a-z0-9-]+)*\.ts\.net)(:\d+)?$")


class AccessTokenMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: str):
        super().__init__(app)
        self.token = token

    async def dispatch(self, request: Request, call_next):
        if not self.token or request.method == "OPTIONS" or request.url.path in OPEN_PATHS:
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        given = auth[7:] if auth.lower().startswith("bearer ") else request.query_params.get("access_token", "")
        if not given or not secrets.compare_digest(given.encode(), self.token.encode()):
            return JSONResponse({"detail": "access token required"}, status_code=401)
        return await call_next(request)
