"""Replay historical recommendations through the strategy pipeline.

Validates SIZING / GATING / SELECTION changes against real outcomes. Does NOT
validate a new forecasting model (no historical model anchors exist).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from services.calculator import calculate_brier_score  # noqa: E402


def load_resolved(path) -> list[dict]:
    """Load resolved markets from performance.json (resolved_markets) or a
    recommendations.json list. Returns rows with a non-null ``outcome``."""
    data = json.loads(Path(path).read_text())
    rows = data["resolved_markets"] if isinstance(data, dict) else data
    return [r for r in rows if r.get("outcome") is not None]


def overall_metrics(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0, "brier": 0.0, "hit_rate": 0.0}
    brier = sum(
        calculate_brier_score(r["ai_estimate"], bool(r["outcome"])) for r in rows
    ) / n
    hits = sum(1 for r in rows if r.get("correct")) / n
    return {"n": n, "brier": round(brier, 4), "hit_rate": round(hits, 4)}
