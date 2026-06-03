import json
import subprocess
import sys
from pathlib import Path

from tools.strategy import evaluate_market, simulate_pnl_per_contract

ROOT = Path(__file__).resolve().parent.parent


def test_evaluate_recommends_clear_edge():
    # Edge must clear EV>=0.10 AND stay within the 0.12 divergence cap. With
    # executable pricing YES edge == (ai - ask), so use a low-priced market to
    # keep the fee small: ai 0.32 vs ask 0.20 -> edge 0.12, fee ~0.011, EV ~0.109.
    d = evaluate_market(
        ai_estimate=0.32, yes_ask=0.20, yes_bid=0.18, confidence="medium"
    )
    assert d["recommend"] is True
    assert d["direction"] == "yes"
    assert d["ev"] >= 0.10


def test_evaluate_rejects_coinflip():
    d = evaluate_market(
        ai_estimate=0.52, yes_ask=0.40, yes_bid=0.38, confidence="medium"
    )
    assert d["recommend"] is False  # 0.42-0.58 hard block


def test_evaluate_rejects_when_ask_eats_edge():
    # mid would show edge, but ask removes it
    d = evaluate_market(
        ai_estimate=0.59, yes_ask=0.585, yes_bid=0.40, confidence="medium"
    )
    assert d["recommend"] is False


def test_simulate_pnl_win_and_loss():
    # YES bought at ask 0.50, resolves YES -> +0.50 profit per contract (1.0-0.50)
    assert simulate_pnl_per_contract("yes", 0.50, outcome=True) == 0.50
    # resolves NO -> lose the 0.50 paid
    assert simulate_pnl_per_contract("yes", 0.50, outcome=False) == -0.50


def test_score_cli_emits_recommendation(tmp_path):
    payload = [{
        "ticker": "TEST-1", "ai_estimate": 0.70,
        "yes_ask": 0.55, "yes_bid": 0.53, "confidence": "medium",
    }]
    f = tmp_path / "in.json"
    f.write_text(json.dumps(payload))
    out = subprocess.check_output(
        [sys.executable, str(ROOT / "tools" / "score.py"), str(f)],
        text=True,
    )
    rows = json.loads(out)
    assert rows[0]["ticker"] == "TEST-1"
    assert "recommend" in rows[0]
    assert rows[0]["direction"] in ("yes", "no", None)
