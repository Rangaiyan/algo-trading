"""Run a backtest campaign in its own process (immune to backend reloads). Results appear on the Backtest Campaign page.

Run from the project root:
    backend\\.venv\\Scripts\\python.exe backend\\run_campaign.py --strategies ICT-3 --timeframes M15 --shortlist 3
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.data.mt5_history import SYMBOLS  # noqa: E402
from app.optimize.pipeline import Job  # noqa: E402
from app.research.campaign import run_campaign  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--symbols", nargs="+", default=SYMBOLS)
ap.add_argument("--timeframes", nargs="+", default=["H1", "H4"])
ap.add_argument("--strategies", nargs="+", default=None)
ap.add_argument("--shortlist", type=int, default=6)
ap.add_argument("--trials", type=int, default=40)
ap.add_argument("--wf-trials", type=int, default=10)
ap.add_argument("--generator", action="store_true")
ap.add_argument("--no-save", action="store_true")
a = ap.parse_args()


class PrintingJob(Job):
    def step(self, msg=None):
        super().step(msg)
        if msg:
            print(msg, flush=True)


job = PrintingJob()
r = run_campaign(a.symbols, a.timeframes, a.strategies, shortlist=a.shortlist, trials=a.trials, wf_trials=a.wf_trials,
                 generator=a.generator, save_passing=not a.no_save, job=job)
print(f"\ncampaign {r['id']}: {len(r['baselines'])} baselines, {len(r['candidates'])} validated, {r['passed']} passed")
for c in r["candidates"]:
    fails = [g["criterion"] for g in c["gate1"] if g["status"] == "fail"]
    print(f"  {c['verdict']:7} {c['strategy']} {c['symbol']} {c['timeframe']}: train PF {c['train']['profit_factor']} "
          f"valid PF {c['validation']['profit_factor']} | fails: {fails}")
print(r["conclusion"])
