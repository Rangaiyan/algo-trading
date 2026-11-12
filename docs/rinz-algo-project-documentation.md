# RINZ ALGO: Final Project Documentation

**Project name:** Rinz Algo
**Version:** 1.0 (Final planning document)
**Date:** 12 November 2026
**Brokers/Platforms:** MetaTrader 5 (MT5) and OANDA
**Primary market:** Forex (Phase 1). Indian Market is supported by design and enabled later via the market switch.
**Strategy families:** SMC (Smart Money Concepts), ICT (Inner Circle Trader concepts), EMA trend strategies, Candlestick patterns, and combinations of them
**Delivery plan:** Build → **1-month backtesting** → **2-month paper trading** → Real (live) trading

---

## Contents

1. Project Overview
2. Master Timeline and Stage Gates
3. Regulatory and Compliance Notes
4. System Architecture and Market Switch
5. Technology Stack
6. Broker Integration: MT5 and OANDA
7. Data Layer
8. Strategy Specifications (SMC, ICT, EMA, Candlesticks)
9. Combined Strategy Engine and Strategy Generator
10. Backtesting Plan (1 Month)
11. Paper Trading Plan (2 Months)
12. Go-Live Plan (Real Trading)
13. Risk Management
14. Telegram Alerts and Control
15. My Investment (Portfolio Tracking)
16. Report Downloads
17. Dashboard and UI
18. Database Design
19. API Design
20. Project Structure
21. Development Roadmap (Build Phases)
22. Testing Strategy
23. Security
24. Deployment and Operations
25. Risks and Mitigations
26. Definition of Done
27. Immediate Next Steps
28. Appendix: Config Examples and Glossary

---

## 1. Project Overview

### 1.1 What Rinz Algo is
Rinz Algo is an algorithmic trading platform that lets you:

1. **Define** trading strategies (SMC, ICT, EMA, candlestick patterns, and combinations).
2. **Backtest** them on historical data with realistic costs.
3. **Generate and optimize** new strategies automatically, with strict overfitting checks.
4. **Paper trade** them on live prices using demo accounts.
5. **Trade live** through MT5 and OANDA once the results justify it.
6. **Monitor** everything on a dashboard and in **Telegram**, track your **investment**, and **download reports**.

### 1.2 Why it exists
You are a trader and an IT professional without time to trade manually. Rinz Algo executes your rules consistently, enforces risk limits, and reports back to you, so trading no longer depends on screen time.

### 1.3 Goals
- One platform for **backtest → paper → live**, running the **same strategy code** in all three modes.
- A **market switch (Forex ⇄ Indian)** across data, costs, symbols, trading hours, and brokers.
- Objective, testable definitions of discretionary concepts (SMC/ICT), so they can be backtested.
- Capital protection first: hard risk limits, kill switch, broker-side stop-losses.
- Full visibility: dashboard, Telegram alerts, investment tracking, downloadable reports.

### 1.4 Non-goals (for now)
- High-frequency or latency-sensitive trading.
- Crypto, copy trading, multi-tenant SaaS/billing.
- Live Indian-market trading (architecture supports it; implementation comes after Forex is proven).

### 1.5 Guiding principles
1. **Same code, three modes:** backtest, paper, live use one strategy interface.
2. **Costs first:** spreads, commissions, swaps, and slippage are always modeled.
3. **No look-ahead:** a signal on a closed candle executes on the next available price.
4. **Validate before trust:** every strategy passes out-of-sample, walk-forward, and Monte Carlo checks.
5. **Safety by default:** live trading is disabled until the stage gates in Section 2 are passed.
6. **Broker is the source of truth** for positions and balances.

---

## 2. Master Timeline and Stage Gates

```
 BUILD (platform)        BACKTEST         PAPER TRADING        LIVE
 ~10-14 weeks     →      1 month    →      2 months     →     small size, then scale
   Gate 0                 Gate 1             Gate 2              Gate 3
```

| Stage | Duration | Environment | Money at risk | Exit gate |
|---|---|---|---|---|
| **Build** | ~10–14 weeks (part-time estimate) | Local/dev | None | Gate 0: engine verified, strategies implemented, alerts working |
| **Backtest** | **1 month** | Historical data | None | Gate 1: at least one strategy passes all validation criteria (Section 10.6) |
| **Paper trading** | **2 months (8+ weeks)** | MT5 demo + OANDA practice, live prices | None (virtual) | Gate 2: live results consistent with backtest, system stable (Section 11.5) |
| **Live trading** | Ongoing | MT5 / OANDA live | Real, **start very small** | Gate 3: scale-up ladder (Section 12.3) |

**Rules**
- A strategy cannot skip a stage. Every strategy follows: `draft → backtested → validated → paper → live → retired`.
- Failing a gate means returning to the previous stage, not forcing the strategy forward.
- The timeline starts counting the backtest month only after the engine is verified against a reference (Gate 0).

> **Note on "1 month of backtesting":** this document treats it as **one month of dedicated testing work** (running, validating, and comparing strategies), not one month of price data. One month of *price data* contains too few trades to prove anything. The backtests must run on **multiple years of historical data** (see Section 7.2 and 10.2), with the month used for structured testing, optimization, and validation.

---

## 3. Regulatory and Compliance Notes

> This is general information, not legal, tax, or financial advice. Verify with qualified professionals.

- **Forex from India:** under FEMA/RBI rules, Indian residents can legally trade forex only on **INR pairs** (USD/INR, EUR/INR, GBP/INR, JPY/INR) through SEBI-regulated exchanges. Trading other pairs through offshore brokers (including via MT5 or OANDA international entities) may fall outside these rules. **Confirm what is permitted for you and which OANDA/MT5 broker entity can legally serve your residency before the live stage.**
- **Backtesting and demo/paper trading** are research and practice activities. The compliance question applies mainly to **live trading**.
- **Algo trading in India** (Indian market, later phase): SEBI has rules for retail algo usage through brokers. Check the broker's policy and current SEBI circulars.
- **Taxes:** the platform keeps a complete trade log and ledger. Consult a tax professional for filing.
- The architecture keeps **live execution switchable per market and per broker**, so it can be enabled only where permitted.

---

## 4. System Architecture and Market Switch

### 4.1 Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                  Frontend (Web dashboard + App)              │
│  Market switch │ Dashboard │ Backtest Lab │ Strategy Studio  │
└──────────────────────────────┬───────────────────────────────┘
                               │ REST + WebSocket
┌──────────────────────────────▼───────────────────────────────┐
│                    Backend API (FastAPI)                     │
│ Auth │ Strategy │ Backtest │ Live │ Risk │ Portfolio │ Reports│
└───────┬──────────────┬──────────────┬─────────────┬──────────┘
        │              │              │             │
  ┌─────▼────┐  ┌──────▼─────┐  ┌─────▼─────┐  ┌────▼───────────┐
  │ Data     │  │ Backtest / │  │ Execution │  │ Notifier       │
  │ Layer    │  │ Optimizer  │  │ Engine    │  │ (Telegram) +   │
  └─────┬────┘  │ (workers)  │  └─────┬─────┘  │ Report builder │
        │       └────────────┘        │        └────────────────┘
  ┌─────▼───────────────┐      ┌──────▼──────────────────────┐
  │ Market Adapters     │      │ Broker Adapters             │
  │  ForexAdapter       │      │  MT5Broker   (Windows)      │
  │  IndiaAdapter(later)│      │  OandaBroker (REST/stream)  │
  └─────────────────────┘      │  SimulatedBroker (backtest) │
                               └─────────────────────────────┘
        │
  ┌─────▼─────────────────────────────────────┐
  │ PostgreSQL (+TimescaleDB) │ Redis │ Files │
  └───────────────────────────────────────────┘
```

### 4.2 The Market Switch
A `MarketAdapter` hides all market differences. The UI switch sets the active market; every API call carries `market=forex|india`.

| Concern | Forex | Indian Market (later) |
|---|---|---|
| Symbols | EURUSD, GBPUSD, USDJPY, XAUUSD, etc. | NIFTY, BANKNIFTY, equities, F&O |
| Hours | 24h Mon–Fri; Asia/London/New York sessions | ~09:15–15:30 IST, holidays |
| Contract specs | Lot size, pip value, leverage | Lot size, tick size, expiry, strike |
| Costs | Spread, commission, swap, slippage | Brokerage, STT, exchange fees, GST, stamp duty |
| Currency | Mixed → account currency | INR |
| Brokers | MT5, OANDA | Zerodha/Upstox/Dhan etc. |

```python
class MarketAdapter(ABC):
    market: str  # "forex" | "india"
    @abstractmethod
    def get_symbols(self) -> list[Instrument]: ...
    @abstractmethod
    def get_historical(self, symbol, timeframe, start, end) -> DataFrame: ...
    @abstractmethod
    def trading_calendar(self) -> Calendar: ...
    @abstractmethod
    def cost_model(self) -> CostModel: ...
    @abstractmethod
    def position_sizer(self) -> PositionSizer: ...
```

---

## 5. Technology Stack

| Area | Choice |
|---|---|
| Language | Python 3.11+ |
| API | FastAPI (async, WebSockets) |
| Data | pandas, NumPy (Polars optional) |
| Indicators | pandas-ta / TA-Lib; custom modules for SMC/ICT |
| Backtesting | Custom event-driven engine + vectorized fast mode for sweeps |
| Optimization | Optuna (Bayesian), DEAP (genetic) |
| Queue/Workers | Celery or RQ + Redis |
| Scheduler | APScheduler |
| Database | PostgreSQL (+ TimescaleDB) and Parquet for candles |
| Frontend | React + TypeScript + Vite + Tailwind |
| Charts | TradingView **Lightweight Charts** (candles, SMC/ICT overlays, trade markers), Recharts/Plotly (equity, heatmaps) |
| Mobile | PWA first, then React Native (Expo) |
| Reports | WeasyPrint (PDF), openpyxl (Excel), pandas (CSV), Jinja2 templates |
| Alerts | Telegram Bot API (python-telegram-bot / aiogram) |
| Infra | Docker, Docker Compose, Nginx + SSL, GitHub Actions, Sentry |
| Hosting | **Windows VPS** for MT5 terminal(s); Linux VPS for core backend/OANDA |

**Skills to develop:** Python (pandas, asyncio), SQL, REST/WebSocket APIs, React/TypeScript, Docker, trading statistics (drawdown, Sharpe, overfitting), VPS administration.

---

## 6. Broker Integration: MT5 and OANDA

### 6.1 Roles of each platform

| | **MT5** | **OANDA** |
|---|---|---|
| Connection | `MetaTrader5` Python package talking to a locally running MT5 terminal | OANDA **v20 REST API** + streaming endpoint |
| OS | **Windows only** (terminal required) | Any OS (pure HTTPS) |
| Strength | Wide broker choice, rich history, MT5-native tools | Clean API, easy practice account, good for cloud/Linux |
| Use in Rinz Algo | Execution + data via a dedicated **Windows MT5 service** | Execution + data from the main backend |
| Paper trading | MT5 **demo account** | OANDA **fxTrade Practice** account |

### 6.2 Recommended topology

```
Linux VPS (core): FastAPI, workers, DB, Redis, Telegram, reports
        │  secure internal API (token + IP allow-list / VPN)
        ▼
Windows VPS: "MT5 Gateway" service (FastAPI) + MT5 terminal
        │
        ▼
     MT5 broker
Core backend ───────────────► OANDA v20 API (direct)
```

The MT5 Gateway exposes a small API (`/account`, `/positions`, `/orders`, `/candles`, `/ticks`) so the rest of Rinz Algo never depends on Windows.

### 6.3 Unified `BrokerAdapter` interface

```python
class BrokerAdapter(ABC):
    name: str
    def connect(self): ...
    def get_account(self) -> Account: ...
    def get_positions(self) -> list[Position]: ...
    def get_candles(self, symbol, timeframe, start, end) -> DataFrame: ...
    def stream_prices(self, symbols, callback): ...
    def place_order(self, order: Order) -> OrderResult: ...   # includes SL/TP
    def modify_order(self, order_id, **changes): ...
    def cancel_order(self, order_id): ...
    def close_position(self, position_id): ...
```

Implementations: `MT5Broker`, `OandaBroker`, `SimulatedBroker`.

### 6.4 Broker-specific notes

**MT5**
- Initialize with `mt5.initialize()`, `mt5.login(account, password, server)`.
- Use `mt5.copy_rates_range()` for candles, `mt5.order_send()` for orders; check `retcode` on every result.
- Symbol names vary by broker (suffixes such as `EURUSD.m`); keep a **symbol mapping table**.
- Respect `volume_min`, `volume_step`, `trade_stops_level` (minimum SL/TP distance), and filling mode (IOC/FOK/RETURN).
- One terminal per account; plan terminals per live/demo account.

**OANDA**
- Auth via a **bearer token**; separate base URLs and tokens for **practice** and **live**.
- Orders are in **units** (not lots): 1 lot = 100,000 units. Sell = negative units.
- Attach `stopLossOnFill` / `takeProfitOnFill` to the order so protection is broker-side.
- Use the **pricing stream** for live prices and **candles endpoint** (granularity such as M1, M5, H1) for history; page requests (max candles per call).
- Respect rate limits; use a persistent session.
- Instrument naming uses underscores (`EUR_USD`); map to internal symbols.

### 6.5 Execution quality tracking
For every order, store requested price, fill price, slippage, spread at entry, latency, and rejection reason. This is compared against backtest assumptions during paper trading (Section 11).

---

## 7. Data Layer

### 7.1 Sources
- **OANDA candles API** (consistent, easy to pull, good for broad history).
- **MT5 history** from the broker you will actually trade with (best match for live execution).
- **Dukascopy** tick/minute data (long history, good for validation).
- **Economic calendar** (Finnhub/Trading Economics) for news filters.

### 7.2 Data requirements for backtesting
- **Pairs (starting set):** EURUSD, GBPUSD, USDJPY, AUDUSD, XAUUSD (adjust to your trading).
- **Timeframes:** M1 (base), then M5, M15, H1, H4, D1 resampled. SMC/ICT needs **multi-timeframe** data (for example H4/D1 for bias, M5/M15 for entries).
- **History length:** **minimum 3 years** (preferably 5), covering trending, ranging, high-volatility, and low-volatility periods.
- **Reserve a final untouched block** (for example the most recent 6 months) as a **hold-out test set** that is never used for tuning.

### 7.3 Pipeline
1. Ingest raw data → 2. Validate (gaps, duplicates, bad ticks, weekend candles) → 3. Normalize to **UTC** → 4. Resample timeframes → 5. Store (Parquet/TimescaleDB) → 6. Tag with a **data version/hash**.

**Time handling is critical for ICT:** store UTC, and convert to **America/New_York** (with daylight-saving rules) when evaluating kill zones and sessions.

### 7.4 Schema

```
candles(market, symbol, timeframe, ts, open, high, low, close, volume, spread)
instruments(id, market, symbol, broker_symbol_map, type, lot_size, tick_size, pip_value, meta)
```

---

## 8. Strategy Specifications

All strategies implement one interface:

```python
class Strategy(ABC):
    params: dict
    def on_start(self, ctx): ...
    def on_bar(self, ctx, bar) -> list[Signal]: ...
    def on_stop(self, ctx): ...
```

SMC and ICT are partly discretionary in practice. To backtest them, Rinz Algo uses **explicit, parameterized, mechanical definitions**. These definitions are interpretations; different traders define the concepts differently, and the parameters let you tune them to match your own approach.

### 8.1 Shared building blocks (market-structure library)

| Block | Mechanical definition (default, configurable) |
|---|---|
| **Swing high/low** | A bar whose high (low) is the highest (lowest) of `n` bars left and right (default n=3, on the chosen timeframe). Confirmed only after `n` bars close (no repainting). |
| **Trend / structure** | Higher highs + higher lows = bullish; lower highs + lower lows = bearish. |
| **BOS (Break of Structure)** | Candle **close** beyond the last swing in the direction of the prevailing trend (trend continuation). |
| **CHoCH / MSS (Change of Character / Market Structure Shift)** | Candle **close** beyond the last swing **against** the prevailing trend (potential reversal). |
| **Displacement** | A strong impulsive candle or sequence with body ≥ `k × ATR(14)` (default k=1.5) that breaks structure. |
| **Liquidity pools** | Equal highs/lows (within tolerance `t × ATR`), previous day/week/month high/low, session highs/lows, Asia range high/low. |
| **Liquidity sweep** | Price trades beyond a liquidity level (wick/close beyond) and then **closes back** inside within `m` bars. |
| **FVG (Fair Value Gap / imbalance)** | 3-candle pattern: bullish when `low[i] > high[i-2]`; bearish when `high[i] < low[i-2]`. Minimum size filter (default ≥ 0.3 × ATR). Mitigated when price trades back into/through it (track partial vs full fill). |
| **Order Block (OB)** | The **last opposite-colored candle** before a displacement that causes a BOS/CHoCH. Zone = candle body (default) or full range. Valid until mitigated or invalidated by a close through it. |
| **Breaker block** | A failed order block that price closes through, then retests from the other side. |
| **Premium / Discount** | Within the current **dealing range** (swing low → swing high), above 50% = premium, below 50% = discount. Longs only in discount, shorts only in premium (optional filter). |
| **Equilibrium** | The 50% level of the dealing range. |
| **HTF bias** | Direction from higher-timeframe structure (D1/H4), previous day high/low behavior, and PD-array location. |

### 8.2 SMC strategies

**SMC-1: Liquidity Sweep + CHoCH + OB/FVG Entry (reversal)**
1. **Bias/context:** HTF (H4/D1) direction or key HTF level (optional filter).
2. **Sweep:** price takes a liquidity pool (for example previous day low or equal lows).
3. **CHoCH/MSS** on the entry timeframe (M5/M15) with displacement.
4. **Entry zone:** the OB or FVG created by the displacement; enter on retrace into the zone (limit at zone edge or 50%).
5. **Stop-loss:** beyond the sweep extreme / OB invalidation point (+ buffer of `x × ATR`).
6. **Take-profit:** next opposite liquidity pool; minimum RR (default ≥ 2).
7. **Filters:** premium/discount alignment, session, spread, news.

**SMC-2: BOS Continuation + OB Retest (trend continuation)**
1. HTF bias aligned with entry-timeframe trend.
2. BOS in trend direction creates an OB/FVG on the pullback leg.
3. Enter on first retest of the OB/FVG in the discount (longs) or premium (shorts).
4. SL beyond OB; TP at previous swing/liquidity or fixed RR.

**SMC-3: FVG Mitigation (imbalance rebalance)**
Trade retracement into an unmitigated FVG aligned with bias, confirmed by a reaction candle (rejection/engulfing).

### 8.3 ICT strategies

**ICT-1: Kill Zone Liquidity Raid (AMD / Power of 3)**
- **Accumulation:** Asia session range (default 20:00–00:00 New York) marks the range high/low.
- **Manipulation:** during the **London kill zone** (default 02:00–05:00 NY) price sweeps one side of the Asia range (Judas swing).
- **Distribution:** after a CHoCH/MSS against the sweep, enter at OB/FVG/OTE; target the opposite side of the range or the next liquidity pool.

**ICT-2: Optimal Trade Entry (OTE)**
- After displacement and structure shift, retrace into the **62%–79% Fibonacci zone** of the impulse leg (default ~70.5% sweet spot), ideally overlapping an FVG/OB.
- SL beyond the 100% of the leg; TP at the previous high/low or extension levels (-0.27, -0.62 as configurable targets).

**ICT-3: Silver Bullet (time-window FVG)**
- Only trade inside defined windows (defaults, New York time): **03:00–04:00**, **10:00–11:00**, **14:00–15:00**.
- Setup: liquidity sweep or displacement, then entry on the first valid FVG in the direction of the intraday draw on liquidity; fixed RR or next liquidity target.

**ICT-4: New York Open Reversal / Daily Bias**
- Daily bias from previous day high/low interaction and HTF PD arrays.
- Take the first aligned setup after the NY open; avoid counter-bias trades.

**Time filters used by ICT strategies** (all configurable, evaluated in New York time with DST): Asia range, London kill zone, New York AM kill zone (default 07:00–10:00), NY PM, and "no-trade" windows around high-impact news and rollover.

### 8.4 EMA strategies

**EMA-1: Trend + Pullback**
- Trend filter: price above EMA 200 (long) / below (short); EMA 20 > EMA 50 for longs.
- Entry: pullback touching/closing near EMA 20 or EMA 50, then a confirmation candle (engulfing or pin bar).
- SL: below the pullback swing (or `1.5 × ATR`); TP: fixed RR (default 2) or trailing by EMA 20.

**EMA-2: Crossover**
- Fast/slow crossover (for example 9/21 or 20/50) with ADX or EMA-200 filter to avoid ranging markets.
- Exit on opposite cross, ATR trailing stop, or fixed RR.

**EMA-3: EMA Ribbon Momentum (optional)**
- Multiple EMAs (8–55) in order and fanning out; enter on shallow pullbacks to the ribbon.

### 8.5 Candlestick pattern strategies

**Pattern detectors (computed on closed candles only):** bullish/bearish **engulfing**, **pin bar/hammer/shooting star**, **inside bar** breakout, **morning/evening star**, **doji** at level, **tweezer top/bottom**, three white soldiers/black crows.

**Rule:** patterns are weak signals alone. Rinz Algo uses them in two ways:
1. **Standalone test strategy** (for baseline comparison): trade pattern + trend filter + SL beyond pattern + fixed RR.
2. **Confirmation layer** (preferred): a pattern **at a meaningful location** (EMA, OB/FVG zone, liquidity sweep level, HTF support/resistance) adds to the confluence score.

Each detector has parameters for body/wick ratios and minimum size relative to ATR to reduce noise.

### 8.6 Strategy parameter summary (examples)

| Strategy | Key parameters |
|---|---|
| SMC-1 | swing `n`, sweep tolerance, displacement `k`, FVG min size, OB zone type, RR, SL buffer, HTF filter on/off |
| SMC-2 | trend TF, OB retest count, premium/discount filter, RR |
| ICT-1 | Asia/London times, sweep tolerance, entry model (OB/FVG/OTE), RR |
| ICT-2 | OTE band (0.62–0.79), target extensions, structure TF |
| ICT-3 | time windows, FVG min size, RR, max trades per window |
| EMA-1 | EMA periods, ATR multiplier, confirmation pattern, RR |
| EMA-2 | fast/slow periods, ADX threshold |
| Candlestick | pattern list, wick/body ratios, min ATR size, location filter |

---

## 9. Combined Strategy Engine and Strategy Generator

### 9.1 Confluence scoring (combine everything)
Instead of one rigid rule set, a strategy can combine factors into a **score**. A trade is taken only when the score passes a threshold.

| Factor | Example weight |
|---|---|
| HTF bias aligned | 2 |
| Liquidity sweep occurred | 2 |
| CHoCH/BOS with displacement | 2 |
| Entry inside OB/FVG | 2 |
| Premium/discount alignment | 1 |
| EMA trend alignment (EMA 50/200) | 1 |
| Candlestick confirmation at zone | 1 |
| Inside kill zone/session | 1 |
| Spread/news filter OK | gating (must pass) |

Weights and the threshold are parameters, and the optimizer can tune them (with validation, to avoid overfitting).

### 9.2 No-code rule builder
Strategies are stored as JSON and interpreted into the `Strategy` interface:

```json
{
  "name": "SMC Sweep + CHoCH + FVG (London)",
  "market": "forex",
  "symbols": ["EURUSD", "GBPUSD"],
  "timeframes": { "bias": "H4", "entry": "M15" },
  "filters": { "sessions": ["london_kz", "ny_am_kz"], "avoid_news": true, "max_spread_pips": 1.5 },
  "setup": { "all": [
    { "block": "liquidity_sweep", "levels": ["prev_day_hl", "asia_hl", "equal_hl"] },
    { "block": "choch", "displacement_atr": 1.5 },
    { "block": "entry_zone", "type": ["fvg", "ob"], "entry": "zone_50" }
  ]},
  "exit": { "stop": "beyond_sweep+0.2atr", "take_profit": { "type": "next_liquidity", "min_rr": 2 } },
  "risk": { "risk_per_trade_pct": 0.5 }
}
```

### 9.3 Strategy generator ("Rinz builds its own strategies")
A **search + validation pipeline**, not magic:

1. **Search space:** building blocks (Section 8), parameter ranges, timeframes, filters, confluence weights.
2. **Generate candidates:** random/grid search, **Optuna** Bayesian optimization, **genetic algorithm** combining blocks.
3. **Score** with a composite objective (Sortino/Sharpe, profit factor, drawdown, trade count, stability), **not raw profit**.
4. **Validate survivors:**
   - Train / validation / **untouched hold-out** split
   - **Walk-forward** analysis
   - **Monte Carlo** (trade reshuffle, randomized costs/slippage)
   - **Parameter sensitivity** (neighbors of best parameters must also work)
   - Cross-pair and cross-regime checks
   - Minimum trade count
   - Multiple-testing awareness (more candidates tried → more lucky winners)
5. **Store** passing strategies in the library with full reports.
6. **Promote** only through the stage gates.

> Auto-generation easily creates curve-fit strategies. The validation step is the most important part.

### 9.4 Strategy lifecycle and versioning
`draft → backtested → validated → paper → live → retired`. Every version stores parameters, data version, backtest results, and status history.

---

## 10. Backtesting Plan (1 Month)

### 10.1 Engine design
- **Event-driven**, bar-by-bar (with optional lower-timeframe intrabar resolution for SL/TP ordering).
- **Vectorized fast mode** for optimization sweeps; finalists are re-run in the event-driven engine.
- **Multi-timeframe aware** (higher-timeframe data aligned without look-ahead).
- **Deterministic:** fixed seeds, saved config, data version hash.

### 10.2 Realism requirements
| Item | Requirement |
|---|---|
| Spread | Variable by time of day/session (use recorded spread data where available) |
| Commission | Per broker (MT5 broker commission; OANDA spread-based pricing) |
| Swap/rollover | Included, with triple swap on Wednesday |
| Slippage | Volatility- and news-aware model |
| Fills | Signal on candle close → fill at next bar/tick; limit orders fill only if price trades **through** the level (configurable) |
| SL/TP same-bar conflict | Conservative rule (assume the worse outcome) or resolve via lower-timeframe data |
| Lot/units rules | MT5 volume step/min; OANDA units |
| Leverage/margin | Broker leverage, margin-call simulation |
| Time | UTC storage, New York conversion with DST for ICT windows |

**Bias traps to prevent:** look-ahead (using unconfirmed swings or future candles), repainting of structure/FVG/OB, optimistic fills, ignoring costs, data snooping.

> **Special SMC/ICT caution:** swing points are only known `n` bars **after** they form. The engine must only use a swing/structure break **after** its confirmation bar. Many chart-based "SMC indicators" repaint and would give inflated backtests.

### 10.3 One-month backtest schedule

| Week | Focus | Output |
|---|---|---|
| **Week 1** | Engine verification and baseline | Cross-check engine vs MT5 Strategy Tester/TradingView on simple EMA strategy (tolerance agreed). Run baseline EMA and candlestick strategies on all pairs. |
| **Week 2** | SMC and ICT implementation tests | Unit-test the structure library (swings, BOS/CHoCH, FVG, OB, sweeps) on hand-labeled charts; run SMC-1/2/3 and ICT-1/2/3 baselines. |
| **Week 3** | Optimization and combination | Parameter optimization, confluence-score tuning, strategy generator runs (on **training** data only). |
| **Week 4** | Validation and selection | Walk-forward, Monte Carlo, sensitivity, **hold-out test** (run once), final ranking, backtest reports, pick strategies for paper trading. |

### 10.4 Metrics produced
Net profit, return, expectancy, win rate, average win/loss, profit factor, payoff ratio, max drawdown (value/%/duration), recovery factor, Sharpe/Sortino/Calmar, trade count, exposure, longest losing streak, monthly/yearly returns, cost breakdown, MAE/MFE, Monte Carlo ranges, per-session and per-pair breakdowns.

### 10.5 Data splitting
```
|---- Training (60%) ----|---- Validation (20%) ----|---- Hold-out test (20%, touched once) ----|
```
Walk-forward: rolling window (for example optimize on 12 months, test on next 3, roll forward).

### 10.6 Gate 1: pass criteria (starting suggestions, adjust to your risk appetite)

| Criterion | Suggested threshold |
|---|---|
| Trades in the total sample | ≥ 100 (≥ 30 in hold-out) |
| Profit factor (net of costs) | ≥ 1.3 |
| Max drawdown | ≤ your tolerance (for example ≤ 15%) |
| Sharpe / Sortino | Sharpe ≥ 1.0 (or Sortino ≥ 1.5) |
| Walk-forward efficiency | ≥ 50% (out-of-sample performance vs in-sample) |
| Hold-out performance | Positive, same direction as training, no collapse |
| Parameter sensitivity | Neighboring parameters remain profitable |
| Monte Carlo | 95th-percentile drawdown within tolerance; profit probability acceptable |
| Cost stress test | Still profitable with spread/slippage worsened by +50% |
| Cross-pair/regime | Not profitable on only one pair or only one market regime (or clearly documented as pair-specific) |

If **no** strategy passes, the correct outcome is "keep researching", not "lower the bar".

---

## 11. Paper Trading Plan (2 Months)

### 11.1 Environment
- **MT5 demo account** (same broker you intend to use live) and **OANDA fxTrade Practice**.
- Live price feeds, **real execution path** (orders go to the demo servers), the **same code, same risk manager, same alerts** as live.
- Run on the **production VPS setup** (Windows VPS for MT5, Linux for core), so infrastructure issues surface early.
- Demo balance set to the **amount you plan to trade live**, so position sizing is realistic.
- Track paper trades separately from live (`mode = paper`).

### 11.2 What is measured
| Area | Metrics |
|---|---|
| Performance | PnL, win rate, profit factor, drawdown, expectancy, per-strategy and per-pair |
| Backtest vs live | Trades per week, average RR, win rate, average hold time versus backtest expectations |
| Execution | Slippage, spread at entry, fill latency, rejection rate (compare to backtest assumptions) |
| Reliability | Uptime, reconnects, missed signals, alert delivery, reconciliation mismatches |
| Risk | Daily loss limit behavior, kill-switch test, news-filter behavior |

### 11.3 Two-month schedule

| Period | Activity |
|---|---|
| **Weeks 1–2** | Shakedown: fix bugs, verify orders/SL/TP, alerts, reconciliation. Run all selected strategies at low frequency. |
| **Weeks 3–6** | Steady-state run. Weekly review of live-vs-backtest drift. No strategy changes (any change restarts that strategy's clock). |
| **Weeks 7–8** | Final evaluation, failure drills (disconnect, restart, rejected order), report generation, go/no-go decision. |

**Discipline rules:** do not tweak parameters mid-test to "improve" results. If a strategy is modified, treat it as a new version and restart its paper period.

### 11.4 Failure drills (must be run at least once)
1. Kill the backend process during an open trade → verify the SL/TP exists broker-side and the system reconciles on restart.
2. Disconnect internet/VPS → alert received, reconnect works.
3. MT5 terminal closed/crashed → watchdog alert and recovery.
4. Broker rejects an order (invalid stops/volume) → handled and alerted, no duplicate orders.
5. Trigger the daily loss limit → trading halts, alert sent.
6. Press the kill switch (dashboard and Telegram) → all positions flattened.
7. High-impact news event → filter behaves as configured.

### 11.5 Gate 2: pass criteria (starting suggestions)

| Criterion | Suggested threshold |
|---|---|
| Duration | ≥ 8 weeks |
| Trades | ≥ 30 per strategy (or a documented reason if the strategy is low-frequency) |
| Performance vs backtest | Win rate, average RR, and profit factor within an agreed band of backtest (for example profit factor ≥ 1.1 and not worse than ~30% below backtest); within Monte Carlo expectations |
| Drawdown | Within the backtest 95th-percentile range |
| Execution | Average slippage/spread within backtest assumptions (or the cost model is updated and the backtest re-run) |
| Reliability | No unhandled errors; reconciliation clean; alerts delivered; all failure drills passed |
| Risk | Limits and kill switch worked as designed |

If Gate 2 fails, update the cost model or strategy, re-validate (Section 10), and repeat paper trading.

---

## 12. Go-Live Plan (Real Trading)

### 12.1 Pre-live checklist
- [ ] Gate 1 and Gate 2 passed and documented.
- [ ] **Compliance confirmed** for the chosen broker/entity and your residency (Section 3).
- [ ] Live API keys are **trade-only** (no withdrawal rights); IP allow-listing enabled where available.
- [ ] Live account funded with an amount you can afford to lose.
- [ ] Risk limits configured (Section 13); kill switch tested on the live setup.
- [ ] Telegram alerts working for the live account; external uptime monitor active.
- [ ] Backups, monitoring, and a documented restore procedure.
- [ ] **Live-enable gate** turned on explicitly, per broker and per strategy.

### 12.2 Launch approach
- Start with **one strategy, one or two pairs**, and the **smallest practical size**.
- Risk per trade **0.25%** initially.
- Daily loss limit tight (for example 1–1.5%) at the start.
- Review every trade for the first two weeks (journal and slippage comparison).

### 12.3 Scale-up ladder (suggested)

| Step | Risk per trade | Condition to advance |
|---|---|---|
| 1 | 0.25% | 4 weeks live, no system issues, results consistent with paper |
| 2 | 0.50% | Another 4 weeks, drawdown within expectation |
| 3 | 0.75–1.0% | Another 8 weeks, stable results; add a second strategy/pair only one at a time |

### 12.4 Stop/rollback rules
Automatically **pause** a strategy (and alert) if any of these occur:
- Drawdown exceeds the backtest 95th-percentile level.
- Live performance falls below an agreed band over a defined trade count.
- Repeated execution errors or abnormal slippage.
- A strategy is paused for review, never "revenge-tuned".

### 12.5 Ongoing governance
- Weekly review (report + Telegram summary), monthly strategy health check, quarterly re-validation on fresh data.
- Retire strategies that decay.

---

## 13. Risk Management

Every signal passes the **Risk Manager** before execution, in paper and live modes alike.

| Control | Detail |
|---|---|
| Position sizing | Fixed fractional (risk % per trade) using SL distance, pip value, and broker lot/unit rules |
| Per-trade risk cap | Default 0.5%; live start 0.25% |
| Max open positions | Global and per symbol; correlation cap (for example no stacked USD exposure beyond a limit) |
| Daily loss limit | Halt for the day when reached |
| Weekly/monthly loss limit | Optional halts |
| Max drawdown stop | Halt all strategies at a threshold and alert |
| Spread/slippage guard | Skip entries if spread exceeds the max (important at rollover and news) |
| News filter | Pause before/after high-impact events |
| Session filters | Strategy-specific (kill zones, windows) |
| Broker-side SL/TP | Always attached at order placement |
| Margin guard | Reject trades if free margin falls below a threshold |
| Max trades per day/strategy | Prevents runaway loops |
| **Kill switch** | Dashboard button and Telegram command; flattens positions and halts |
| Duplicate-order protection | Unique client order IDs, idempotent order handling |

---

## 14. Telegram Alerts and Control

### 14.1 Setup
1. Create a bot with **@BotFather**, copy the token.
2. Get your chat ID (for example via **@userinfobot**).
3. Put both in `.env`; allow-list chat IDs:
   ```
   TELEGRAM_BOT_TOKEN=xxxxxxxx
   TELEGRAM_CHAT_IDS=123456789
   ```
4. Optional: a private group with topics (Trades, Risk, System, Reports).

### 14.2 Alert categories

| Category | Severity | Examples |
|---|---|---|
| Trade | Info | Order placed/filled/modified, SL/TP hit, position closed with PnL |
| Signal | Info | Signal generated (and whether the risk manager accepted it) |
| Risk | Warning/Critical | Daily loss limit, drawdown threshold, margin low, kill switch |
| System | Warning/Critical | Broker disconnected, feed stale, order rejected, VPS restart, MT5 terminal down |
| Strategy | Info | Started/stopped/promoted, validation passed/failed |
| Backtest/Optimizer | Info | Job completed, candidate found |
| Portfolio | Info | Daily summary, new equity high, deposit/withdrawal recorded |
| Market | Info | Session open, high-impact news approaching |

### 14.3 Message examples

```
🟢 TRADE OPENED · FOREX · LIVE
EURUSD BUY 0.20 lot @ 1.08420
SL 1.08220 · TP 1.08820 · Risk 0.25% ($25)
Strategy: SMC-1 Sweep+CHoCH v3 · Broker: OANDA
```
```
✅ TRADE CLOSED · FOREX · PAPER
EURUSD BUY 0.20 lot · +$80.40 (+0.8%)
Entry 1.08420 → Exit 1.08820 (TP) · Held 5h 12m
Today: +$112.30 · Equity: $10,412.50
```
```
🚨 RISK · DAILY LOSS LIMIT HIT
Loss today: -$150 (1.5% limit reached). Trading halted for today.
```
```
⚠️ SYSTEM · MT5 DISCONNECTED
Connection lost 14:32:10 UTC. Retrying (2/10).
```

### 14.4 Telegram commands

| Command | Action |
|---|---|
| `/status` | Health, active market, mode, running strategies |
| `/market forex` / `/market india` | Switch active market context |
| `/positions` | Open positions with floating PnL |
| `/pnl` | Today/week/month PnL |
| `/investment` | Capital, equity, net P/L snapshot |
| `/report daily|weekly|monthly` | Generate and send the report file |
| `/trades 20` | Last N trades |
| `/pause <strategy>` / `/resume <strategy>` | Control a strategy |
| `/killswitch` | Flatten and halt (confirmation required) |
| `/risk` | Risk usage |
| `/help` | Command list |

**Safety:** allow-listed chat IDs only; two-step confirmation (inline buttons with expiry) for destructive actions; optional PIN/TOTP for kill switch and go-live; audit log of every command; never send API keys, passwords, or full account numbers (bot chats are not end-to-end encrypted).

### 14.5 Delivery design
```
Any module → Event(type, severity, market, mode, payload)
           → Event bus (Redis pub/sub)
           → Notification service: routing, dedupe, rate limit, formatter
           → Telegram sender (async, retry/backoff) → alerts_log
```
- Rate-limit aware (about 1 message/second per chat); Critical alerts have priority; Info alerts can be silent.
- Deduplicate repeated errors into one alert with a counter.
- Queue messages during outages and send on recovery; optional email fallback.
- Quiet hours (only Critical alerts sound); heartbeat message plus an **external uptime monitor**, because a dead server cannot report itself.

### 14.6 Code sketch

```python
class TelegramNotifier:
    API = "https://api.telegram.org/bot{token}/{method}"
    def __init__(self):
        self.token = os.environ["TELEGRAM_BOT_TOKEN"]
        self.chat_ids = os.environ["TELEGRAM_CHAT_IDS"].split(",")
        self.queue = asyncio.Queue()

    async def send(self, text, severity="info", file_path=None):
        await self.queue.put((text, severity, file_path))

    async def worker(self):
        async with httpx.AsyncClient(timeout=20) as client:
            while True:
                text, severity, file_path = await self.queue.get()
                for chat_id in self.chat_ids:
                    for attempt in range(5):
                        try:
                            if file_path:
                                with open(file_path, "rb") as f:
                                    r = await client.post(
                                        self.API.format(token=self.token, method="sendDocument"),
                                        data={"chat_id": chat_id, "caption": text[:1024]},
                                        files={"document": f})
                            else:
                                r = await client.post(
                                    self.API.format(token=self.token, method="sendMessage"),
                                    json={"chat_id": chat_id, "text": text,
                                          "disable_notification": severity == "info"})
                            if r.status_code == 429:
                                await asyncio.sleep(r.json()["parameters"]["retry_after"]); continue
                            r.raise_for_status(); break
                        except Exception:
                            await asyncio.sleep(2 ** attempt)
                await asyncio.sleep(1.1)
```

---

## 15. My Investment (Portfolio Tracking)

Answers: *How much have I invested, what is it worth now, and how has it performed?* Works per market, per broker (MT5/OANDA), and combined, with **Live vs Paper** kept separate.

### 15.1 Tracks
- **Capital ledger:** deposits, withdrawals, fees, transfers (date, amount, currency, account, note).
- **Accounts:** MT5 account(s), OANDA account(s), later Indian demat/trading accounts.
- **Positions/holdings:** entry, size, SL/TP, floating PnL, margin used, swap.
- **Performance:** realized/unrealized PnL, costs, equity curve, drawdown, best/worst day.

### 15.2 Metrics

| Metric | Definition |
|---|---|
| Total invested | Deposits − withdrawals |
| Current value | Balance + floating PnL (equity) |
| Net profit | Current value − invested (+ withdrawals taken) |
| Return % | Net profit / invested |
| **TWR** (time-weighted return) | Strategy performance, unaffected by deposit/withdrawal timing |
| **XIRR** (money-weighted) | Your actual outcome including cash-flow timing |
| Max drawdown | Peak-to-trough equity decline |
| Allocation | By market, broker, strategy, pair |
| Strategy contribution | PnL per strategy |
| Costs | Spread, commission, swap, taxes/charges |
| Currency view | Account currency per account; combined view converted with a stored FX rate (rate and date shown) |

### 15.3 Page layout
Top cards (Invested, Current Value, Net Profit, Today's PnL, Max Drawdown) → equity curve with cash-flow markers → allocation charts → positions table → returns (TWR, XIRR, monthly heatmap) → capital ledger (add/edit/export) → optional goal tracker. Controls: market switch, Live/Paper toggle, broker filter.

### 15.4 Sync
Pull balance/equity/positions from MT5 and OANDA on a schedule and at each fill (broker = source of truth). Manual or CSV entry for deposits/withdrawals the API does not expose. Reconcile against broker statements and flag differences.

---

## 16. Report Downloads

### 16.1 Report catalog

| Report | Contents | Formats |
|---|---|---|
| Daily summary | Trades, PnL, win rate, open positions, risk usage | PDF, Telegram message |
| Weekly/Monthly performance | Returns, equity curve, drawdown, per-strategy/pair breakdown, costs | PDF, Excel |
| Trade history | Every trade with SL/TP, PnL, fees, strategy, notes | CSV, Excel |
| Investment statement | Ledger, invested vs current value, TWR/XIRR, allocation | PDF, Excel |
| Realized PnL statement | Date-wise realized gains/losses with costs (input for tax filing; consult a professional) | Excel, CSV |
| Backtest report | Config, data range/version, costs, metrics, equity curve, trades, heatmap, Monte Carlo | PDF, HTML, Excel |
| Validation report | Walk-forward, sensitivity, hold-out result, pass/fail per criterion | PDF |
| Paper-trading evaluation | Live-vs-backtest comparison, execution quality, drill results, Gate 2 verdict | PDF |
| Risk report | Limit usage, drawdowns, breaches, kill-switch events | PDF |
| Audit/alerts log | Orders, setting changes, alert history | CSV |

Filters: market, mode (Backtest/Paper/Live), broker, account, strategy, date range.

### 16.2 Delivery
1. **Dashboard:** Reports page with a Download button (PDF/Excel/CSV).
2. **Telegram:** `/report daily|weekly|monthly` sends the file (bots can upload up to ~50 MB; larger files via dashboard link).
3. **Scheduled:** daily (after the NY close), weekly (Saturday), monthly (1st), pushed to Telegram and/or email.
4. **History:** all generated reports stored and re-downloadable (signed, expiring links).

### 16.3 Generation
PDF via WeasyPrint + Jinja2, Excel via openpyxl (multiple sheets, native charts), CSV via pandas, charts via Matplotlib/Plotly images. Heavy reports run as **background jobs**; the user is notified when ready.

Every report states: market, mode, broker, date range, currency, **gross/net of costs**, FX rates used, data version, generation time, and this disclaimer: *"Backtested and past performance do not guarantee future results. This is not investment or tax advice."*

### 16.4 Endpoints
```
POST /reports                         GET /reports
GET  /reports/{id}/status             GET /reports/{id}/download?fmt=pdf|xlsx|csv
POST /reports/schedules
GET  /investment/summary              GET/POST /investment/ledger
GET  /investment/equity-curve?from=&to=
```

---

## 17. Dashboard and UI

### 17.1 Global elements
- **Market switch (Forex ⇄ Indian)** in the top bar (Indian items disabled until that phase).
- **Mode badge:** Backtest / Paper / **LIVE** (clear warning colour).
- Broker/account selector, notifications, **kill-switch button**.

### 17.2 Pages
1. **Overview:** equity curve, daily PnL, open positions, running strategies, risk usage, broker connection health (MT5/OANDA).
2. **Data Manager:** symbols, timeframes, date coverage, gaps, import/update, quality report.
3. **Strategy Studio:** templates (SMC/ICT/EMA/Candlestick), rule builder, code editor, parameter forms, versioning.
4. **Chart Lab:** Lightweight Charts with **SMC/ICT overlays**: swings, BOS/CHoCH labels, FVG and OB boxes, liquidity lines, kill-zone shading, EMA lines, candlestick pattern markers, trade entries/exits with SL/TP. Used to **visually verify** that the mechanical definitions match what you see on a chart.
5. **Backtest Lab:** configure, run, results (equity, drawdown, trades, metrics, heatmaps), compare runs.
6. **Optimizer/Generator:** search space, objective, leaderboard, validation report with pass/fail badges.
7. **Strategy Library:** status, version, key metrics, promote/demote/retire (stage-gate enforced).
8. **Paper/Live Trading:** positions, orders, fills, live chart with SL/TP, per-strategy start/stop, risk status, logs.
9. **Paper-trading Scorecard:** live-vs-backtest comparison, execution quality, drill checklist, Gate 2 status.
10. **My Investment:** (Section 15).
11. **Reports:** (Section 16).
12. **Trade Journal:** notes, tags, screenshots, export.
13. **Settings:** broker connections (encrypted keys), risk rules, Telegram, report schedules, base currency, user profile.

---

## 18. Database Design

```
users(id, email, password_hash, role, created_at)
broker_accounts(id, user_id, market, broker[mt5|oanda], mode[paper|live], credentials_encrypted, status)
accounts(id, user_id, market, broker, currency, mode, name, status)
instruments(id, market, symbol, broker_symbol_map, type, lot_size, tick_size, pip_value, meta)
strategies(id, user_id, name, family[smc|ict|ema|candle|combo], market, definition_json, status, created_at)
strategy_versions(id, strategy_id, version, params_json, code_ref, stage, created_at)
backtest_runs(id, strategy_version_id, market, symbols, timeframe, start, end,
              cost_config, data_version, metrics_json, status, created_at)
backtest_trades(id, run_id, symbol, side, entry_ts, exit_ts, entry_px, exit_px, qty, pnl, fees, mae, mfe)
optimization_runs(id, strategy_id, search_space, objective, status, results_json)
validation_reports(id, strategy_version_id, walk_forward, monte_carlo, sensitivity, holdout, passed)
stage_gates(id, strategy_version_id, gate, passed, criteria_json, evaluated_at, approved_by)
live_sessions(id, strategy_version_id, broker_account_id, mode, started_at, stopped_at)
orders(id, session_id, client_order_id, broker_order_id, symbol, side, type, qty, price, sl, tp,
       requested_px, fill_px, slippage, latency_ms, status, ts)
trades(id, session_id, symbol, side, entry_ts, exit_ts, entry_px, exit_px, qty, pnl, fees, notes)
cash_flows(id, account_id, type, amount, currency, fx_rate_to_base, ts, note)
equity_snapshots(id, account_id, ts, balance, equity, margin_used, unrealized_pnl)
holdings(id, account_id, symbol, qty, avg_cost, ltp, unrealized_pnl, updated_at)
fx_rates(ts, pair, rate)
reports(id, user_id, type, market, mode, params_json, formats, status, created_at)
report_schedules(id, user_id, type, cron, channels, enabled)
risk_events(id, session_id, type, detail, ts)
alerts_log(id, channel, category, severity, message, ts)
audit_log(id, user_id, action, detail, ts)
```

---

## 19. API Design

All endpoints accept/derive `market` (`forex` | `india`).

```
POST   /auth/login
GET    /markets
GET    /instruments?market=forex
GET    /brokers                         # MT5/OANDA connection status
GET    /data/candles?market=&symbol=&tf=&start=&end=
POST   /data/import

GET/POST /strategies                    GET/PUT /strategies/{id}
POST   /strategies/{id}/versions
POST   /strategies/{id}/promote         # stage-gate enforced
POST   /backtests                       GET /backtests/{id}   GET /backtests/{id}/trades
POST   /backtests/compare
POST   /optimizations                   GET /optimizations/{id}/leaderboard
POST   /strategies/{id}/validate        # walk-forward, Monte Carlo, hold-out

POST   /live/start    # mode=paper|live (live requires gate + confirmation)
POST   /live/stop
POST   /live/kill-switch
GET    /live/positions    GET /live/orders
GET/PUT /risk/settings

POST   /reports    GET /reports/{id}/download?fmt=pdf|xlsx|csv
GET    /investment/summary    GET/POST /investment/ledger
WS     /ws/prices    WS /ws/live-events
```

---

## 20. Project Structure

```
rinz-algo/
├── backend/
│   ├── app/
│   │   ├── api/                  # FastAPI routers
│   │   ├── core/                 # config, security, logging
│   │   ├── markets/
│   │   │   ├── base.py           # MarketAdapter
│   │   │   ├── forex/            # sessions, pip math, cost model
│   │   │   └── india/            # (later) calendar, charges
│   │   ├── brokers/
│   │   │   ├── base.py           # BrokerAdapter
│   │   │   ├── mt5.py            # talks to MT5 Gateway
│   │   │   ├── oanda.py          # v20 REST + stream
│   │   │   └── simulated.py
│   │   ├── data/                 # ingestion, storage, resampling, quality
│   │   ├── indicators/           # EMA, ATR, ADX...
│   │   ├── structure/            # swings, BOS/CHoCH, FVG, OB, liquidity, sessions/kill zones
│   │   ├── patterns/             # candlestick detectors
│   │   ├── strategies/
│   │   │   ├── base.py
│   │   │   ├── smc/  ict/  ema/  candle/  combo/
│   │   │   └── rule_engine/      # JSON → Strategy
│   │   ├── backtest/             # engine, metrics, cost models
│   │   ├── optimize/             # Optuna/GA, walk-forward, Monte Carlo
│   │   ├── execution/            # order manager, reconciler, scheduler
│   │   ├── risk/                 # sizing, limits, kill switch
│   │   ├── alerts/               # notifier, Telegram bot/commands, templates
│   │   ├── portfolio/            # ledger, snapshots, TWR/XIRR
│   │   ├── reports/              # PDF/Excel/CSV builders, schedules
│   │   ├── gates/                # stage-gate evaluation
│   │   ├── models/               # SQLAlchemy models
│   │   └── workers/              # Celery tasks
│   ├── tests/
│   └── alembic/
├── mt5-gateway/                  # Windows service wrapping MetaTrader5 package
├── frontend/                     # React + TS dashboard
├── mobile/                       # PWA → React Native
├── infra/                        # Docker, Nginx, CI, deployment scripts
├── docs/
└── README.md
```

---

## 21. Development Roadmap (Build Phases)

Timelines assume roughly one developer working part-time alongside a job; adjust as needed.

| Phase | Duration | Deliverables |
|---|---|---|
| **0. Foundation** | 1–2 weeks | Repo, Docker, Postgres/Redis, FastAPI skeleton, CI; `MarketAdapter`/`BrokerAdapter` interfaces; **Telegram notifier + `/status`**; UI shell with market switch |
| **1. Data + Engine** | 3–4 weeks | MT5 Gateway + OANDA adapters (data), ingestion/quality checks, forex cost model, event-driven backtest engine, metrics, EMA and candlestick strategies, Backtest Lab UI |
| **2. SMC/ICT library** | 3–4 weeks | Structure library (swings, BOS/CHoCH, FVG, OB, liquidity, premium/discount, sessions/kill zones in NY time), Chart Lab overlays for visual verification, SMC-1/2/3 and ICT-1/2/3 |
| **3. Builder + Optimizer** | 2–3 weeks | Rule builder, Optuna, walk-forward, Monte Carlo, sensitivity, strategy library and stage gates |
| **4. Generator** | 2 weeks | Genetic/block-combination search, confluence scoring, validation pipeline |
| **5. Execution + Risk + Dashboard** | 3–4 weeks | MT5/OANDA order execution (demo), reconciliation, risk manager, kill switch, full Telegram alerts/commands, My Investment, reports, scheduled reports |
| **Gate 0** | | Engine verified against a reference; all components tested |
| **Backtest stage** | **1 month** | Section 10 |
| **Paper stage** | **2 months** | Section 11 |
| **Live stage** | Ongoing | Section 12 |
| **Later** | | Indian Market adapter and brokers; mobile app (PWA → React Native) |

Phases 3–5 can overlap with early backtesting where sensible, but **paper trading must run on the finished execution and risk system**.

---

## 22. Testing Strategy

- **Unit tests:** indicators, cost models, position sizing, pip/unit math, metrics, TWR/XIRR.
- **Structure library tests:** hand-labeled chart fixtures for swings, BOS/CHoCH, FVG, OB, sweeps; **non-repainting tests** (results must not change when future bars are appended).
- **Engine tests:** hand-calculated tiny scenarios; look-ahead detection tests.
- **Reference cross-check:** compare a simple strategy to MT5 Strategy Tester / TradingView within tolerance.
- **Integration tests:** MT5 demo and OANDA practice (orders, SL/TP, modify, close, reconciliation).
- **Failure drills:** Section 11.4.
- **Report/alert tests:** every alert category and report type generated and delivered.
- **CI:** run unit tests and linting on every commit.

---

## 23. Security

- Broker credentials/API keys encrypted at rest; secrets in `.env`/secret manager; never committed.
- **Trade-only API keys** (no withdrawal permission); IP allow-listing where supported.
- JWT auth, HTTPS only, rate limiting, role-based access, optional 2FA for the dashboard.
- MT5 Gateway reachable only from the core backend (VPN/IP allow-list + token).
- Telegram: allow-listed chat IDs, confirmations/PIN for destructive commands; no secrets or account numbers in messages.
- Reports: access-controlled storage, signed expiring download links, optional auto-delete.
- Audit log for every order, setting change, kill-switch event, and Telegram command.
- Daily database backups and a tested restore procedure.
- Rotate keys periodically and immediately if exposed.

---

## 24. Deployment and Operations

- **Environments:** local → staging (demo/practice accounts) → production.
- **Containers:** backend, workers, frontend, Postgres, Redis via Docker Compose on a Linux VPS.
- **Windows VPS:** MT5 terminal(s) plus MT5 Gateway; auto-start on reboot; terminal watchdog.
- **Monitoring:** health endpoints, Sentry, log aggregation, **external uptime monitor**, Telegram alerts for disconnects/errors/limits, MT5 terminal heartbeat.
- **Time sync:** NTP on all servers (important for session/kill-zone logic).
- **Backups:** daily DB backups, report archive, configuration in version control.
- **Runbook:** documented steps for restart, failover, broker outage, and "flatten everything" procedure.

---

## 25. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Overfitted strategies | Hold-out set, walk-forward, Monte Carlo, sensitivity, minimum trades, multi-test awareness |
| **Repainting/look-ahead in SMC/ICT logic** | Confirmed-swing logic only, non-repainting tests, visual verification in Chart Lab |
| Subjective definitions of SMC/ICT | Explicit parameterized definitions, documented interpretations, parameters tuned and validated |
| Backtest vs live mismatch | Realistic costs, paper stage, execution-quality comparison, cost-model updates |
| Short test window | Multi-year data, hold-out, strict gates (the "1 month" is work time, not data length) |
| Bugs causing losses | Tests, small initial size, hard limits, broker-side SL/TP |
| Connection/terminal failure | Reconnect logic, watchdog, broker-side stops, alerts, external uptime monitor |
| Time zone/DST errors (ICT windows) | UTC storage, NY-time conversion tests across DST changes |
| Broker symbol/lot differences | Symbol mapping table, volume-step/min checks, stop-level validation |
| Bad data | Quality checks, multiple sources (OANDA/MT5/Dukascopy), gap detection |
| Regulatory issues | Section 3: verify before live |
| Emotional overrides | Rules-based gates; no mid-test parameter tweaking; documented rollback rules |
| Scope creep | Forex first; Indian market only after Forex is stable |
| Single-developer bottleneck | Clean interfaces, documentation, automated tests |

---

## 26. Definition of Done

**Platform**
- Market switch works end-to-end; adding India requires only a new adapter and cost model.
- A strategy runs unchanged in backtest, paper, and live.
- MT5 and OANDA adapters pass integration tests on demo/practice accounts.
- Backtest results match a reference within the agreed tolerance.
- Structure library (swings, BOS/CHoCH, FVG, OB, liquidity, sessions) is non-repainting and verified visually and by tests.

**Operations**
- Every alert category reaches Telegram within seconds with correct market, mode, and broker labels.
- Telegram commands work only from allow-listed chats; kill switch tested end-to-end.
- Investment totals match broker statements within tolerance; TWR/XIRR verified on test cases.
- Every report type downloads in its listed formats; scheduled reports deliver automatically.

**Process**
- Gate 1 (backtest) and Gate 2 (paper) passed and documented before any live trade.
- Live-enable requires explicit confirmation; stop/rollback rules active.

---

## 27. Immediate Next Steps

1. **Confirm compliance** for the broker/entity you will use live (MT5 broker and OANDA entity) given your residency (Section 3).
2. Open **demo/practice accounts**: an MT5 demo account with your intended broker, and an OANDA fxTrade Practice account; generate the OANDA API token.
3. Set up the repository, Docker Compose, FastAPI skeleton, and the **Telegram bot** (Phase 0).
4. Provision a **Windows VPS** (for MT5) and a Linux VPS (or start locally).
5. Pull 3–5 years of data for 3–5 pairs; build and verify the data pipeline.
6. Implement the backtest engine with the forex cost model; cross-check with one simple EMA strategy.
7. Build the **structure library** with Chart Lab overlays and test it on hand-labeled charts.
8. Define your **own** exact SMC/ICT rules (your OB definition, your kill-zone times, your entry model) in the config so the code matches how you trade.
9. Proceed through Gate 0 → 1-month backtest → 2-month paper → live.

---

## 28. Appendix

### 28.1 Example strategy config (YAML)

```yaml
strategy:
  id: rinz_smc_sweep_v1
  family: smc
  market: forex
  symbols: [EURUSD, GBPUSD]
  timeframes: { bias: H4, entry: M15 }
  structure:
    swing_n: 3
    displacement_atr_mult: 1.5
    fvg_min_atr: 0.3
    ob_zone: body            # body | full_range
    sweep_tolerance_atr: 0.2
  filters:
    sessions: [london_kz, ny_am_kz]       # evaluated in America/New_York
    max_spread_pips: 1.5
    avoid_news_minutes: { before: 30, after: 30 }
    premium_discount: true
  entry:
    model: fvg_or_ob
    order_type: limit
    entry_level: zone_50
  exit:
    stop: beyond_sweep_plus_0.2atr
    take_profit: { type: next_liquidity, min_rr: 2.0 }
    breakeven_at_rr: 1.0
  risk:
    risk_per_trade_pct: 0.25
    max_trades_per_day: 2
  confluence:
    threshold: 7
    weights: { htf_bias: 2, sweep: 2, choch: 2, zone: 2, pd_array: 1, ema_trend: 1, candle_confirm: 1, session: 1 }
```

### 28.2 Stage-gate checklist (printable)

| Gate | Item | Done |
|---|---|---|
| 0 | Engine matches reference within tolerance | ☐ |
| 0 | Structure library non-repainting and verified | ☐ |
| 0 | Alerts, kill switch, reconciliation working on demo | ☐ |
| 1 | Multi-year backtest with costs completed | ☐ |
| 1 | Walk-forward, Monte Carlo, sensitivity, hold-out passed | ☐ |
| 1 | Backtest and validation reports generated | ☐ |
| 2 | ≥ 8 weeks paper trading on MT5 demo + OANDA practice | ☐ |
| 2 | Live-vs-backtest within agreed band | ☐ |
| 2 | Execution quality matches cost assumptions | ☐ |
| 2 | All failure drills passed | ☐ |
| 3 | Compliance confirmed | ☐ |
| 3 | Trade-only keys, limits set, kill switch tested live | ☐ |
| 3 | Starting at minimum risk with the scale-up ladder | ☐ |

### 28.3 Glossary

| Term | Meaning |
|---|---|
| **SMC** | Smart Money Concepts: trading framework based on market structure, liquidity, and institutional order flow ideas |
| **ICT** | Inner Circle Trader concepts: time-and-price framework (kill zones, OTE, AMD, etc.) |
| **BOS** | Break of Structure (trend continuation) |
| **CHoCH / MSS** | Change of Character / Market Structure Shift (potential reversal) |
| **FVG** | Fair Value Gap: three-candle imbalance |
| **OB** | Order Block: last opposite candle before a displacement |
| **Liquidity** | Resting stop orders above highs/below lows (equal highs/lows, previous day/week levels) |
| **Sweep / Raid** | Price takes liquidity then reverses back |
| **Premium/Discount** | Upper/lower half of a dealing range relative to equilibrium (50%) |
| **OTE** | Optimal Trade Entry: 62–79% retracement zone |
| **Kill zone** | Time windows of high activity (London, New York) |
| **AMD / Power of 3** | Accumulation, Manipulation, Distribution |
| **TWR / XIRR** | Time-weighted / money-weighted return |
| **Walk-forward** | Repeated optimize-then-test on rolling out-of-sample windows |
| **Monte Carlo** | Randomized resampling of trades/costs to estimate outcome ranges |
| **Paper trading** | Trading with live prices on a demo/practice account, with no real money |

---

*Disclaimer: Trading leveraged instruments such as forex involves a high risk of loss, and you can lose more than you expect. Backtested and paper-trading results do not guarantee future live performance. This document is a technical plan and does not constitute financial, legal, or tax advice.*
