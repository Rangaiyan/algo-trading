"""Usage: python scripts_backtest.py EMA-2 [--source store --symbol EURUSD --tf M15]"""
import argparse
import json

from app.backtest import runner

ap = argparse.ArgumentParser()
ap.add_argument("strategy")
ap.add_argument("--symbol", default="EURUSD")
ap.add_argument("--tf", default="M15")
ap.add_argument("--source", default="synthetic")
ap.add_argument("--days", type=int, default=150)
a = ap.parse_args()
print(json.dumps(runner.run(a.strategy, a.symbol, a.tf, a.source, a.days), indent=2))
