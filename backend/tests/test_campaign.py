"""Backtest-stage campaign: baselines -> shortlist -> validation -> report (synthetic data, tiny settings)."""
import json

from app.data import pipeline as P
from app.optimize import pipeline as OP
from app.research import campaign as C


def test_campaign_end_to_end(tmp_path, monkeypatch):
    df = P.synthetic(days=200)
    hold = df.index[int(len(df) * 0.9)]
    ins = df[df.index < hold]
    cut = ins.index[int(len(ins) * 0.75)]
    split = {"df": df, "meta": {"holdout_start": str(hold), "data_version": "syn"}, "insample": ins,
             "train": ins[ins.index < cut], "valid": ins[ins.index >= cut], "holdout": df[df.index >= hold]}
    monkeypatch.setattr(OP, "load_split", lambda s, tf: split)
    monkeypatch.setattr(C, "ROOT", tmp_path / "campaigns")
    monkeypatch.setattr(C, "GATE0_FILE", tmp_path / "gate0_last.json")
    monkeypatch.setattr(C, "MIN_BASELINE_TRADES", 5)
    job = OP.Job()
    r = C.run_campaign(["EURUSD"], ["M15"], ["EMA-1", "EMA-2", "CANDLE-1"], shortlist=2, trials=3, wf_trials=0,
                       save_passing=False, job=job)
    assert len(r["baselines"]) == 3 and len(r["shortlist"]) == 2
    assert len({b["strategy"] for b in r["shortlist"]}) == 2            # diversity: different strategies first
    assert len(r["candidates"]) == 2 and all("gate1" in c for c in r["candidates"])
    assert r["gate0"]["status"] == "not run" and r["conclusion"]
    assert json.loads((tmp_path / "campaigns" / f"{r['id']}.json").read_text())["id"] == r["id"]
    assert C.list_campaigns()[0]["id"] == r["id"] and C.get_campaign(r["id"])["baselines"]
    (tmp_path / "gate0_last.json").write_text(json.dumps({"verdict": "pass", "summary": {"match_rate": 0.97}}))
    assert C.gate0_status()["status"] == "pass"
