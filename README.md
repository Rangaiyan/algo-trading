# Rinz Algo

Algo trading platform: backtest → paper → live (MT5 + OANDA). Full plan: `docs/rinz-algo-project-documentation.md`.

## Run locally
```bash
cp .env.example .env
cd backend && uv venv .venv && uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/uvicorn app.main:app --reload      # http://localhost:8000/docs
.venv/bin/pytest -q && .venv/bin/ruff check .
cd ../frontend && npm install && npm run dev  # http://localhost:5173
```
Postgres/Redis: `docker compose up db redis` (not needed yet in Phase 0).

## Status
Phase 0 (Foundation) done: interfaces, forex sessions (NY/DST), SimulatedBroker, Telegram notifier + /status, UI shell.
Next: Phase 1 (data pipeline + backtest engine).
