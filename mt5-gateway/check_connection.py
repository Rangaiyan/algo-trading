"""Quick check that Python can talk to the running MT5 terminal.

Run (with the MT5 terminal open and logged in to your demo account):
    .venv\\Scripts\\python.exe check_connection.py
"""
import MetaTrader5 as mt5

TERMINAL = r"C:\Program Files\MetaTrader 5\terminal64.exe"

if not mt5.initialize(path=TERMINAL):
    raise SystemExit(f"initialize() failed: {mt5.last_error()}")

try:
    term = mt5.terminal_info()
    acc = mt5.account_info()
    print("Terminal :", term.name, "| connected:", term.connected,
          "| algo trading allowed:", term.trade_allowed)
    if acc is None:
        raise SystemExit(f"No account logged in: {mt5.last_error()}")
    trade_mode = {0: "DEMO", 1: "CONTEST", 2: "REAL"}.get(acc.trade_mode, acc.trade_mode)
    print("Account  :", acc.login, "|", acc.server, "|", trade_mode)
    print("Balance  :", acc.balance, acc.currency, "| leverage 1:", acc.leverage)

    symbols = mt5.symbols_get("*EURUSD*") or []
    print("EURUSD symbol names on this broker:", [s.name for s in symbols])
    if symbols:
        name = symbols[0].name
        mt5.symbol_select(name, True)
        tick = mt5.symbol_info_tick(name)
        print(f"Last tick {name}: bid={tick.bid} ask={tick.ask}" if tick else "No tick yet")
        rates = mt5.copy_rates_from_pos(name, mt5.TIMEFRAME_H1, 0, 3)
        print("Last 3 H1 bars:", None if rates is None else [tuple(r)[:5] for r in rates])
finally:
    mt5.shutdown()
