import json
from pathlib import Path

from tools.backtest import load_resolved, overall_metrics

ROOT = Path(__file__).resolve().parent.parent


def test_reproduces_performance_json_brier_and_hitrate():
    perf = json.loads((ROOT / "data" / "performance.json").read_text())
    rows = load_resolved(ROOT / "data" / "performance.json")
    assert len(rows) == perf["total_resolved"]  # 360
    m = overall_metrics(rows)
    assert abs(m["brier"] - perf["overall_brier"]) < 1e-3   # 0.2111
    assert abs(m["hit_rate"] - perf["hit_rate"]) < 1e-3     # 0.4722


def test_load_resolved_filters_unresolved():
    rows = load_resolved(ROOT / "data" / "performance.json")
    assert all(r.get("outcome") is not None for r in rows)
