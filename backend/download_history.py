"""Download real candle history from MT5 (via the gateway) into data_store/.

Run from the project root, with the MT5 terminal logged in and mt5-gateway/start.ps1 running:
    backend\\.venv\\Scripts\\python.exe backend\\download_history.py                 # all pairs, all timeframes, 5 years
    backend\\.venv\\Scripts\\python.exe backend\\download_history.py --symbols EURUSD --timeframes M15 H1
Re-running only fetches what is new.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.backtest.runner import DATA_ROOT  # noqa: E402
from app.data.mt5_history import SYMBOLS, TIMEFRAMES, download_all  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--symbols", nargs="+", default=SYMBOLS)
ap.add_argument("--timeframes", nargs="+", default=TIMEFRAMES)
ap.add_argument("--years", type=float, default=5)
a = ap.parse_args()

results = download_all(DATA_ROOT, a.symbols, a.timeframes, a.years)
print(f"\n{'symbol':8} {'tf':4} {'bars':>9}  {'from':10}  {'to':10}  {'years':>5}  quality")
for m in results:
    if "error" in m:
        print(f"{m['symbol']:8} {m['timeframe']:4} {'-':>9}  ERROR {m['error']}")
        continue
    q = m["quality"]
    print(f"{m['symbol']:8} {m['timeframe']:4} {m['bars']:>9,}  {m['start'][:10]}  {m['end'][:10]}  {m['years']:>5}  "
          f"{'OK' if q['ok'] else 'ISSUES'} {' '.join(q['issues'])}")
