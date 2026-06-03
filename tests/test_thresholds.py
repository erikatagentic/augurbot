"""The EV floor and divergence cap must be tunable so the backtester can sweep
them. Defaults must reproduce the current hardcoded 0.10 / 0.12 behavior."""
from services.calculator import should_recommend
from tools.strategy import evaluate_market


def test_should_recommend_respects_custom_divergence():
    # ai 0.70 vs price 0.55 -> divergence 0.15. Default cap 0.12 rejects.
    assert should_recommend(0.20, "medium", 0.70, 0.55) is False
    # Loosen the cap to 0.20 -> divergence passes, EV 0.20 clears 0.10.
    assert should_recommend(0.20, "medium", 0.70, 0.55, max_divergence=0.20) is True


def test_should_recommend_respects_custom_ev_threshold():
    # EV 0.06 fails the default 0.10 floor for medium (divergence 0.05 is fine).
    assert should_recommend(0.06, "medium", 0.70, 0.65) is False
    # Lower the floor to 0.05 -> passes.
    assert should_recommend(0.06, "medium", 0.70, 0.65, ev_threshold=0.05) is True


def test_evaluate_market_threads_thresholds():
    # ai 0.70, ask 0.55, bid 0.53: default divergence 0.15 > 0.12 -> reject.
    assert evaluate_market(0.70, 0.55, 0.53, "medium")["recommend"] is False
    # Loosen divergence -> recommended (edge 0.15, ev ~0.133).
    d = evaluate_market(0.70, 0.55, 0.53, "medium", max_divergence=0.20)
    assert d["recommend"] is True
    assert d["direction"] == "yes"
