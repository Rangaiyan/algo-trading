# Rinz Algo

Algo trading platform: backtest → paper → live (MT5 only; OANDA is not available to Indian residents). Full plan: `docs/rinz-algo-project-documentation.md`.

## Run locally
```bash
cp .env.example .env
cd backend && uv venv .venv && uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/uvicorn app.main:app --reload      # http://localhost:8000/docs
.venv/bin/pytest -q && .venv/bin/ruff check .
cd ../frontend && npm install && npm run dev  # http://localhost:5173
```
Postgres/Redis: `docker compose up db redis` (not needed yet; data is stored as Parquet in `data_store/`).

## Market data (real history from MT5)
Broker: **Deriv via MT5** (`Deriv-Demo`). With the MT5 terminal logged in and `mt5-gateway/start.ps1` running:
```bash
backend\.venv\Scripts\python.exe backend\download_history.py      # 5 pairs x M1..D1, 5 years; re-run to top up
```
or use **Market Data → Download** in the app. Each set is stored as `data_store/<SYMBOL>/<TF>.parquet` plus a
`.meta.json` (range, quality report, data version hash, hold-out start, broker swap/spread spec).
MT5 caps history at "Max bars in chart" (100,000 by default), which limits M1/M5; set it to Unlimited for more.

## Status
- **Phase 0 (Foundation): done.** Interfaces, forex sessions (NY/DST), SimulatedBroker, Telegram notifier + /status, UI shell.
- **Phase 1 (Data + Engine): done.** MT5 gateway + `MT5Broker` data side (account, positions, candles, prices);
  real Deriv history for EURUSD/GBPUSD/USDJPY/AUDUSD/XAUUSD (M15 ~4 y, H1/H4/D1 5 y); validation, UTC, version hash,
  6-month hold-out; forex cost model with broker swap rates, triple-swap day and a typical-spread floor; event-driven
  engine + metrics; strategies EMA-1, EMA-2, EMA-3, CANDLE-1 (pattern list: engulfing, pin bar, star, tweezer,
  three candles, inside-bar breakout; doji detector for later confluence use); Backtest Lab on real data.
  OANDA was dropped (not available in India).
- **Phase 2 (SMC/ICT library): done.** `app/structure/`: swings (confirmed after n bars), trend, BOS/CHoCH on close,
  displacement, order blocks, breakers, FVGs (touch / fill / invalidation), liquidity pools (PDH/PDL, PWH/PWL, Asia
  range, swing and equal highs/lows) and sweeps, premium/discount, H4 bias from closed bars only, New York kill zones
  with DST. Every object records the bar it became known; tests prove nothing changes when later candles are added.
  Engine supports limit orders (with expiry). Strategies SMC-1/2/3 and ICT-1/2/3 (magic 4001-4003 / 3001-3003).
  **Chart Lab** page draws all of it on real candles for visual checking. ICT-4 (NY open / daily bias) not built yet.
- **Phase 3 (Builder + Optimizer): done.** Engine loop rewritten on arrays (~15x faster, identical results).
  `app/optimize/`: Optuna search on the training split only (first 75% before the hold-out), composite score
  (Sharpe, profit factor, drawdown, min trades), validation split, rolling walk-forward (efficiency), Monte Carlo
  (trade bootstrap + random extra costs), parameter sensitivity, +50% cost stress, cross-pair, Gate 1 checklist.
  `app/library/`: strategy library in `strategy_library/*.json` with lifecycle draft -> backtested -> validated ->
  paper -> live -> retired (validated needs Gate 1 incl. the one-time hold-out; live needs Gate 2). Rule builder
  (`app/strategies/rules.py`): JSON blocks, all-must-pass or confluence score. Pages: Rule Builder, Optimiser,
  Strategy Library.
- **Phase 4 (Strategy Generator): done.** `app/generate/genetic.py`: candidates are Rule Builder specs (blocks,
  options, confluence weights/threshold, entry, exit, structure). Genetic search (tournament selection, crossover,
  mutation, elitism) or random search, scored on the training split only; the best distinct designs are validated
  with the full Phase 3 pipeline plus a multiple-testing luck benchmark (expected best Sharpe of N skill-less
  strategies). Page: Strategy Generator; survivors can be opened in the Rule Builder or saved to the library.
- **Phase 5 (Execution + Risk + Dashboard): done.** Gateway order endpoints (market/limit, close, modify, cancel) with
  a DEMO-ONLY guard (`MT5_ALLOW_LIVE_ORDERS=false`), mandatory broker-side stop-loss, broker volume/stop-distance rules
  and idempotent client ids. `app/risk/manager.py`: sizing from equity and stop distance, daily/weekly loss halts,
  drawdown halt, max positions / per pair / USD exposure, margin and spread guards, trades-per-day cap, kill switch.
  `app/execution/engine.py`: strategy sessions on live MT5 candles every 15 s, reconciliation with MT5 (fills, SL/TP
  closes, expired limits, unknown positions), execution-quality log, equity snapshots, daily summary; state in
  `runtime/` (git-ignored). Telegram commands (/status /positions /pnl /investment /trades /risk /report /pause /resume
  /killswitch with confirmation, audit log). My Investment (TWR, XIRR, drawdown, ledger) and Reports (CSV, printable
  HTML). Pages: Live Trading, My Investment, Reports; the top-bar Kill switch is live. Set `TRADING_ENGINE_ENABLED=false`
  to stop the engine entirely.
- **Gate 0 tooling: ready (needs one Strategy Tester run).** `mt5-gateway/mql5/RinzGate0.mq5` (installed and compiled
  into MT5 as Experts\Rinz\RinzGate0) and `app/strategies/reference.py` (GATE0) implement the same EMA-cross rules;
  `app/gates/gate0.py` matches the tester's trades with the Rinz engine's one by one (match rate, entry/exit prices,
  P&L, profit factor). Page: Gate 0 Check. Engine now treats MT5 candles as BID prices (buys pay the full spread and
  exit on the bid), and only one process can run the trading loop (runtime/engine.lock).
- **Next:** run Gate 0 in the Strategy Tester, the paper-trading shakedown and failure drills (plan section 11.4),
  then the backtest stage: no strategy passes Gate 1 yet.
