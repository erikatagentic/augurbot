import json
from pathlib import Path

from tools.backtest import load_resolved, overall_metrics

ROOT = Path(__file__).resolve().parent.parent


def test_reproduces_performance_json_brier_and_hitrate():
    # performance.json reports total_resolved=360 but ONE row
    # (KXATPMATCH-26FEB22FILLEH-FIL, a dropped-Tennis market) has outcome=null
    # while still being baked into its stored aggregates — a results.py data
    # bug. load_resolved correctly excludes it, so we expect 359 resolvable
    # rows. Our independent metrics over those 359 reproduce the canonical
    # 0.2111 / 0.4722 to within the swing caused by that one excluded row.
    perf = json.loads((ROOT / "data" / "performance.json").read_text())
    rows = load_resolved(ROOT / "data" / "performance.json")
    assert len(rows) == perf["total_resolved"] - 1   # 360 - 1 null-outcome row
    m = overall_metrics(rows)
    assert abs(m["brier"] - perf["overall_brier"]) < 5e-3    # ~0.2108 vs 0.2111
    assert abs(m["hit_rate"] - perf["hit_rate"]) < 5e-3      # ~0.4735 vs 0.4722


def test_load_resolved_filters_unresolved():
    rows = load_resolved(ROOT / "data" / "performance.json")
    assert all(r.get("outcome") is not None for r in rows)
