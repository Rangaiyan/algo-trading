"""Optimise + validate a basket (one rule set, shared settings, several pairs) in its own process and save it to the
Strategy Library if it passes Gate 1 (hold-out pending).

Run from the project root:
    backend\\.venv\\Scripts\\python.exe backend\\run_basket.py ICT-3 H1 EURUSD GBPUSD USDJPY AUDUSD
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.library import store  # noqa: E402
from app.optimize.basket import run_basket_pipeline  # noqa: E402
from app.optimize.pipeline import Job  # noqa: E402

strategy, timeframe, symbols = sys.argv[1], sys.argv[2], sys.argv[3:]
trials = 40
job = Job()
r = run_basket_pipeline(strategy, symbols, timeframe, trials=trials, wf_trials=10, job=job)
out = Path("runtime") / "baskets"
out.mkdir(parents=True, exist_ok=True)
path = out / f"{strategy}_{timeframe}_{'+'.join(symbols)}.json"
path.write_text(json.dumps(r, indent=1, default=str))
print(f"{strategy} {timeframe} basket {'+'.join(symbols)}: verdict {r['verdict']}")
print(f"  tuned {r['tuned']}")
for k in ("train", "validation", "insample", "cost_stress"):
    m = r[k]
    print(f"  {k:11} trades {m['trades']:4} PF {m['profit_factor']} return {m['return_pct']}% DD {m['max_drawdown_pct']}% sharpe {m['sharpe']}")
print("  members in-sample:", {s: (m["trades"], m["profit_factor"]) for s, m in r["members"]["insample"].items()})
for g in r["gate1"]:
    print(f"  {g['status']:7} {g['criterion']}: {g['value']}")
if r["verdict"] in ("pass", "pending"):
    e = store.create(f"Basket {strategy} {timeframe} {'+'.join(symbols)}", strategy, "+".join(symbols), timeframe, r["params"], report=r)
    print("saved to the Strategy Library:", e["id"])
print("report:", path)
