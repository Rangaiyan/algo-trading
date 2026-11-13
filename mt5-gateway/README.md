# MT5 Gateway (Windows only)

Small FastAPI service next to the MT5 terminal (doc section 6.2). The core backend calls it over HTTP.

## Setup (once)
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env   # then set MT5_GATEWAY_TOKEN to a long random string
```

## Run
1. Open the MT5 terminal and log in to the demo account.
2. `.\start.ps1` (API docs: http://127.0.0.1:9000/docs)
   - If the backend runs in Docker: `.\start.ps1 -BindHost 0.0.0.0` and set
     `MT5_GATEWAY_URL=http://host.docker.internal:9000` in the backend `.env`.

Quick check without the server: `.\.venv\Scripts\python.exe check_connection.py`

## Endpoints (all need `Authorization: Bearer <token>` except /health)
`/health`, `/status`, `/account`, `/positions`, `/symbols/{name}`,
`/candles?symbol=EURUSD&timeframe=H1&start=...&end=...`, `/ticks?symbols=EURUSD,GBPUSD`.
All times are UTC (broker server offset auto-detected). `/orders` is Phase 5.
