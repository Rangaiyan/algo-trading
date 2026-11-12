# UI reference → Rinz Algo (Forex) feature map

Source: 32 screenshots of an Indian options algo-desk app ("PHOENIX", dark "MONO DARK" theme).
Rule: copy structure, interactions and look; replace everything Indian-market-specific with forex.
Status key: ✅ built · 🔨 in progress · ⬜ planned · ❓ menu name only (no screenshot, behaviour inferred)

## 0. Global substitution table

| Reference (India) | Rinz Algo (Forex) |
|---|---|
| NIFTY / SENSEX index filter | Symbol / group filter: EURUSD, GBPUSD, USDJPY, AUDUSD, XAUUSD · Majors / Minors / Metals / All |
| CE / PE (call / put) | LONG / SHORT (BUY / SELL) |
| Strike, premium, moneyness, expiry, delta ("prem per index pt") | Entry price, MFE/MAE in pips, R-multiple, swap days held. Dropped: strike, expiry, moneyness |
| Lots of 65 / 60 | Lots (0.01 step) + units, pip value per lot |
| ₹ with lakh/crore grouping, "L"/"k" | Account currency, 1,234,567 grouping, K/M; pips shown beside money |
| STT / brokerage / GST ("costs ≈") | Spread + commission + swap + slippage |
| 09:15–15:30 IST, "KNOWN AT 09:15", 03:15 PM auto square-off | 24×5 market, Sydney/Tokyo/London/New York sessions (DST-correct), session-open info, Friday-close flatten |
| Weekend OFF toggles (Sat/Sun) | Market closed Fri 17:00 → Sun 17:00 New York; per-session enable toggles |
| Expiry days | High-impact news days (NFP/FOMC/CPI), rollover days |
| Overnight / carry | Held over 17:00 NY rollover (swap; triple on Wednesday) |
| FYERS broker pill | MT5 + OANDA pills with connection dot |
| Paper / Live book | Demo / Live (MT5 demo, OANDA practice vs live) |
| Desks: Index Options, Ultimatum, Zone | Desks by strategy family: **EMA**, **ICT**, **SMC** (+ **Candle** as a 4th desk) |
| Points | Pips |
| "legs" | trades |
| Gap at 09:15 | Weekend gap / session-open gap |

## 1. Global shell (identical on all 32 screens)

Top bar (~38px): logo + app name + date · live clock (seconds) · env badge DEV/DEMO/LIVE · MENU (purple, opens drawer) · desk shortcut pills AURITH / CHRONICLE / EMA / ICT / SMC (each its own colour) · broker pills with status dot (MT5, OANDA) · API latency bar · account chip · ADMIN chip · right cluster: offset/notification counter, LABELS toggle, Aa font size, theme chip (MONO DARK + other themes), privacy eye, logout.
Forex additions: UTC + broker server time, active-session pill (Sydney/Tokyo/London/NY, overlap highlight), kill-switch button, Demo/Live mode badge.
Left icon rail (~28–40px): collapse chevron, star (favourites), then one icon per page; active page = filled square + left accent bar.
Drawer: "PIN OPEN", "★ FAVORITES", full page list, hover chevron, dims page behind.
Branded route loader: logo + ring + "waking the desk" + thin progress bar.
Look: bg ≈ #0b0b12, panels ≈ #12121a, border ≈ #23232f, accent violet #8b5cf6, green #22c55e, red #ef4444, amber #f59e0b, cyan #2dd4bf; monospace, 9–11px uppercase micro-labels, 6–12px radius, very dense.

## 2. Pages

### Aurith — live home dashboard ⬜ (screenshot 15-50-36)
Sub-toolbar: book selector, SCENE (decorative confetti), AI toggle, FRESH (data freshness dot), FOCUS, FULL, DEMO, CAPSULE, TOOLS, layout preset (MAIN). Hero: P&L today, mood line, status pill ("ON FIRE"), grade badge, booked / floating / peak / low. Left: THE DESKS tiles (P&L + open count), BY SYMBOL running P&L (long/short split, open, trade count), THE DAY DRAWN (sparkline), HIGH & LOW WATER, STILL ON THE TABLE (open positions: side, lots, held time, in→now, peak, best, "giving X% of it", low; list/card toggle, pager, CHAT, ANALYSE). Centre: ASK THE DESK (LLM chat over your data, A-/A+ font, markdown, SEND), THE AI READ (risk cards: open risk with no stops, gap rift, loss leak). Right: session clock + timeline, PROFIT BOOKED HOUR BY HOUR, THE EDGE grid (avg/trade, win rate, R:R, avg win/loss, held W/L, best hour, fell from top), THE MEDAL SHELF (best trades), SETTINGS.
Forex adds: equity, balance, margin used, free margin, margin level %, leverage, spread now, swap.

### Dashboard / Career overview ✅ (15-47-28, 15-47-37)
Built on the demo ledger. Not built: SCENE/FOCUS/CAPSULE modes, CHAT. Account tiles show "—" until a broker is connected.
Toolbar: FOCUS, book (Demo/Live), desks filter, sessions filter, CHAT, DEMO, last-refresh, SETTINGS. Hero career P&L (since date · trades · win% · days · avg/day · today booked + floating · open count). Cards: CAREER (sparkline), TODAY (high/low, kept %), THIS WEEK (Mon–Fri bars, vs last), THIS MONTH (progress bar, vs last). KPI tiles: WIN RATE, STREAK (best/worst run), AVG DAY, MAX LOSS (symbol/date), BEST DAY, WORST DAY, DEEPEST DIP, LONG/SHORT P&L, HIGH WATER, LOWEST, PROFIT FACTOR (+expectancy), W/L (avg win/loss), COSTS ≈ (per trade), NET AFTER COSTS. THE DAYS · LAST 30 (bars with values), THE WEEKS bars, THE MONTHS bars, THE WEEKS · LAST 12 cards (booked/floating/trades/win%/long-short/high-low), THE MONTHS · LAST 4 cards. Footer: refresh cadence (today live 15s, history 60s).

### Desk pages: EMA Desk / ICT Desk / SMC Desk (+ Candle Desk) 🔨 (15-43-36 … 15-45-22)
Built: EMA + Candle desks (session cards/strip/table, filters, lifecycle controls, chart with markers, past-trades 4 views, trade-detail modal, THE RECORD, deep links). ICT/SMC show an empty state until Phase 2. Not built: NEW SESSION, DESK/SESSION PDF (need execution/reports), FLIP/PUSH (strategy-specific to the reference), TODAY-ON-SYMBOL leg ladder, open-position card (demo trades are all closed), per-session trading toggles.
Header (eyebrow, title, rule description). Buttons: NEW SESSION, PREBUILT & SCHEDULES, ARCHIVE, EDGE, DESK PDF, refresh. Status tabs ALL / LIVE / PAPER(→DEMO) / ANY STATE / ACTIVE / STOPPED. Session toggles (per-session enable instead of weekend OFF). View switch CARDS / STRIP / TABLE. REFINE dropdowns: symbol, timeframe, risk, size, session, setup, settings; counter "n of m sessions"; SHOWING chips (BOOK x), CLEAR ALL.
Session card: symbol tag, mode badge, RUNNING badge, name; chips (timeframe, sides, risk/target, lots, rule code, re-entry, ignition, rungs/ladder, max loss), ends-in line, NET P&L, BOOKED/OPEN split, peak/low, win bar W/L %, TODAY / PREV DAY / PER TRADE, "since" start time. Selected card actions: PDF, PAUSE, RESUME, STOP, ARCHIVE (state-dependent enable; STOP offers "close all positions").
Selected-session live panel: summary strip (open now, booked today, day high/low, price, net today), toolbar HIDE CHART / FLIP / PUSH / LABELS / SETTINGS / JUMP TO, candlestick chart (bar countdown, markers: entries, exits, zone LURE/TAP/rule-IN/rule-OUT, PUSH levels), position card (side, entry, best, peak profit, given back, kept % of peak, lowest, hard stop, rule stop, price now/peak/low, lots, time in, swap) + CLOSE POSITION.
FIND A PAST TRADE: search, CARDS / TABLE / LEDGER / CALENDAR, ANALYTICS, ENTERED/EXITED basis, day / side / win-loss filters, equity mini-sparkline, day-grouped trade cards (in→out, % / pips, in/out time, held, overnight flag, kept of best, peak, gave back, SHORT/LONG chip, exit reason, DETAIL).
Trade-detail modal: header + P&L; KPI tiles (pips, peak profit, given back, booked); "how far each travelled" bars; timeline (low, bought, out, peak); price section (peak/lowest price, MFE/MAE); entry/exit context; capture ratio; entered/exited/held (+candles held, overnight); footer broker ticket + session id.
THE RECORD (session ledger summary, PDF, NET NOW) and TODAY ON SYMBOL (live leg ladder, LINES / MARKS / LABELS toggles).
Forex adds: spread at entry, slippage, commission, swap, margin used, pip value, MAE/MFE in pips, session of entry.

### Prebuilt & Schedules ⬜ (15-45-37, 15-45-52)
Filter chip groups (rule family + counts, mode, symbol, scheduled/manual). Buttons: NEW FROM EMA / ICT / SMC, EDGE, REFRESH. THE WEEK AHEAD: next-run summary, rows by time with day-of-week dot matrix, repeat label, card chips (rocket = armed, ↻ = recurring, red dot = live). Setup cards (family badge, symbol badge, mode badge): entry/risk, timeframe, sides, lots, flat-by time, recurring flag, VIEW & EDIT SETTINGS, SCHEDULES list (time, weekday, OK status, enable/disable, delete), ADD SCHEDULE, LAUNCH NOW, DUPLICATE, delete. Schedules in UTC with session presets (London open, NY open…).

### FX Analytics ⬜ (15-46-09 … 15-46-45)
Filters: 7D/30D/90D/ALL, rule family, mode, session filter; EDGE / ARCHIVE / REFRESH. KPI strip: NET P&L, WIN RATE, AVG/TRADE, PER DAY, LONG, SHORT, BEST, WORST, CAPTURE. JUMP TO anchors (CALENDAR, EQUITY, LONG VS SHORT, WHEN, OUTCOMES, LEVERAGE, CONSISTENCY, GIVE-BACK). 4-month P&L calendar heat-map (month totals, green/red day counts, day P&L + trade count). Equity curve + daily histogram + stats (ending, peak, trough, max drawdown, green/red days). LONG VS SHORT two-sides cards with insight sentence. BY WEEKDAY and BY ENTRY HOUR diverging bars (hour-of-day 24h + session overlay). Outcome histogram (worst → best). LEVERAGE section → effective leverage & margin usage. BY ENTRY bands (by spread, stop distance, lot size). BY SYMBOL cards. Day-by-day cards grid (green/red border, trades, win, per trade, long/short chips, capture).

### Edge ⬜ (15-46-57, 15-47-04)
Toolbar: LENS (Settings / Pairs), WHEN, DESK, BOOK, SYMBOL; Dashboard / Archive / Refresh. Hero: N setups, sessions merged by settings, trades, pips, per-trade pips, P&L, % green; verdict bar KEEP / PROMISING / WATCH / WEAK / DROP / TOO EARLY with counts; best proven edge; concentration check (best trade vs the rest). THE SETUP MAP bubble scatter (pips/trade vs trades, log x, "judging starts" line, keep/drop zones). Cards/Archive cards/Table/Form views, RANK by verdict / pips per trade / total pips / P&L / profit factor / win % / trades / recent form / form rating, search, hide empty, "only KEEP" chip. Setup card: verdict, desk, name (+merged count), P&L, pips, settings string, sparkline, per-trade, PF, win, dip, trades·sessions·date range, "improving lately", book split.

### Time Machine ⬜ (15-48-30 … 15-49-01)
Control bar: date prev/next, symbol (one / All), book, keyboard hints (Space / ← → / [ ]). Hero: weekday + date, today P&L, high; chips (regime e.g. Sideways, range ×normal, trades, desks); desk FOCUS pills. Chart card: 1-minute candles, layer toggles (Trades, Best moments, Given back, Exposure, Signals), half-hour P&L strip, crosshair, volume, P&L sub-chart (booked + open, per-desk lines). Side panel: AT THIS MOMENT / TODAY SO FAR (clock, P&L, long/short exposure bar, desk cards with sparkline, LATEST MOMENTS list with reason codes e.g. GIVEBACK FLOOR HIT, STOP). Playback bar: prev/pause/next, 10× / 60× / 300×, readout, scrubber with activity histogram, event ticks, hover tooltip. THE CHAPTERS: tabs Autopsy / Story / Legs / Signals / Log / Notes; 12 auto insight cards (Given back, Best half-hour, Best trade, Leaning against, Piling in, Worst half-hour, Straight back in, Worst trade…) each with ▶ jump-to chip.

### Market Weather ⬜ (15-49-44, 15-49-50)
Filters: symbol, WHEN, BOOK, SESSIONS. Hero: today's regime ("Mild drift"), tiles MOVE / RANGE× / CLOSED AT % / PIPS / YOUR TRADES; desk advice per regime (Switch on / Caution / Sit out). AT THE OPEN: gap up / flat / gap down cards with desk results + share of days. Controls: Report cards / Leaderboard / Bubble matrix; BY desk / strategy / setup / session; WEATHER kind of day / how it opened / news day / range; SHOW P&L / per day / pips per trade / win %. Banners: BIGGEST EDGE, BIGGEST LEAK, MOST WEATHER-DEPENDENT. Strategy cards (run-on / stay-off pills, mini bars per weather). THE CLIMATE: every trading day, bar = wildness, news-day markers, streak brackets. Forecaster rule: ≥3 days, profitable, ≥55% green = run on; losing and ≤45% green = stay off.

### The Clock ⬜ (15-49-11)
Filters WHEN / symbol / book; TIME BY entry|exit; DESK. Polar 24h dial with session arcs (green/red wedges), centre total. Insight cards (best half-hour, worst, before/after cut-off, held over rollover). "IF YOU STOPPED ENTERING AT…" curve.

### Rulebook Lab ⬜ (15-49-29)
Filters + START FROM presets (As traded, No entries after X, Book at +$, London only, Day stop, N trades/day, Tilt guard, Combined, Your rulebook). Rule toggles: Desks; No entries before/after; Skip weekdays; Skip days opening gap/flat; Skip news days; Max trades/day; Day stop at booked loss/profit; tilt stop; cool-down. THE RESULT: rulebook vs as-traded P&L, skipped count, equity chart with difference band + hover; KPI strip P&L / TRADES / WIN RATE / WORST DAY / DEEPEST DIP / GREEN DAYS.

### Desk Orchestra ⬜ (15-50-03)
Desk-combination scatter (worst fall vs final P&L, smoothest / richest), equity curves of combinations, loss-correlation matrix ("when one loses, does the other?"), per-desk daily P&L heat-map (30 days, scrollable). Forex adds: pair-exposure correlation (EURUSD vs GBPUSD), USD-stacking warning.

### Chart Desk ⬜ (15-50-12, 15-50-24, 15-50-50)
Session tabs; NEW SESSION (symbol search with 3-letter search + "your symbols", timeframe 1m…60m + 4h/D1, DEMO/LIVE); header stats (price, % on day, day range, open P&L, booked today, FEED status); AUTO FLAT time; STOP; candlestick chart with OHLC legend, indicator chips (e.g. EMA 7), bar countdown; draggable TARGET / ENTRY / STOP lines with pips, %, money and R:R; zones. SETUPS panel: target/entry/stop steppers, lots + risk %, STOP EXITS ON touch|candle close, ENTER WITH market|limit|stop|both, ARM – WATCH FOR ENTRY, ONLY THIS / HIDE / DELETE. LEDGER: TRADES / ACTIVITY, NET, N, WIN RATE, PF, AVG WIN/LOSS, BEST/WORST. Empty states ("no historical data", "market closed").

### ❓ Money Left, Level Lab (was Strike Lab), Signal Funnel, Chronicle, Session Archive
No screenshot of their contents. Planned from their names and the doc: Money Left = MFE vs realised ("profit left on the table"); Level Lab = entry/SL/TP level optimisation; Signal Funnel = signals → risk-accepted → filled → profitable; Chronicle = trade journal (doc §17 Trade Journal); Archive = stopped sessions list. **Confirm before building.**

## 3. Rinz Algo pages from the original doc that the reference lacks
Backtest Lab ✅ · Strategy Studio / rule builder · Chart Lab (SMC/ICT overlays) · Data Manager · Optimizer/Generator · Strategy Library (stage gates) · Paper-trading Scorecard (Gate 2) · My Investment · Reports · Settings (brokers, risk, Telegram, schedules) · Kill switch · Risk dashboard (daily loss, drawdown, exposure).

## 4. Forex-only features to add everywhere relevant
Margin, free margin, margin level, leverage; spread / swap / commission / slippage lines; pip value and lot sizing by risk %; session clock + overlaps; news calendar blackout; broker connection per MT5/OANDA; kill switch; daily-loss / drawdown halts; correlation / USD-stacking exposure; weekend-gap handling; multi-currency account conversion.

## 5. Data the UI needs from the backend (build before most pages)
trade ledger with: symbol, side, lots, entry/exit time+price, pnl net, pips, fees (commission, swap, spread), MFE, MAE, peak time, desk/strategy, session id, exit reason, mode, session-of-entry · sessions table · equity snapshots · positions · setups/schedules · market-day regime table (range ×ATR, gap, news flag) · candles API · event log. Reference screens show a few cosmetic items kept low priority: SCENE confetti, theme chip variants, Aa font size.
