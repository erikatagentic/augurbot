"""Tests for performance analytics — failure classification + risk metrics."""
from services.analytics import (
    FAIL_BAD_ESTIMATE,
    FAIL_EXTERNAL_SHOCK,
    FAIL_NEWS_TIMING,
    classify_failure,
    profit_factor,
    sharpe,
)


# ── classify_failure ──

def test_correct_bet_not_a_failure():
    assert classify_failure(0.7, 0.65, outcome=True, correct=True) is None


def test_bad_estimate_default():
    # We said 0.70 YES, outcome NO. Market was 0.55 (closer-ish), no big shock,
    # no adverse clv -> our estimate was the problem.
    out = classify_failure(0.70, 0.55, outcome=False, correct=False, clv=0.0)
    assert out == FAIL_BAD_ESTIMATE


def test_external_shock_when_market_also_very_wrong():
    # Market priced YES at 0.85 but outcome was NO -> market err 0.85 > 0.55.
    out = classify_failure(0.80, 0.85, outcome=False, correct=False, clv=-0.02)
    assert out == FAIL_EXTERNAL_SHOCK


def test_news_timing_on_adverse_clv():
    # Market wasn't wildly off, but the line moved hard against us post-entry.
    out = classify_failure(0.60, 0.52, outcome=False, correct=False, clv=-0.15)
    assert out == FAIL_NEWS_TIMING


def test_shock_takes_priority_over_clv():
    # Both a big market miss AND adverse clv -> shock wins.
    out = classify_failure(0.80, 0.90, outcome=False, correct=False, clv=-0.20)
    assert out == FAIL_EXTERNAL_SHOCK


def test_clv_none_falls_to_bad_estimate():
    out = classify_failure(0.65, 0.50, outcome=False, correct=False, clv=None)
    assert out == FAIL_BAD_ESTIMATE


# ── sharpe ──

def test_sharpe_zero_when_too_few():
    assert sharpe([0.1]) == 0.0
    assert sharpe([]) == 0.0


def test_sharpe_zero_variance():
    assert sharpe([0.05, 0.05, 0.05]) == 0.0


def test_sharpe_positive_series():
    s = sharpe([0.1, 0.2, 0.15, 0.05, 0.12])
    assert s > 0


def test_sharpe_negative_mean_negative_sharpe():
    assert sharpe([-0.1, -0.05, -0.2, -0.15]) < 0


# ── profit_factor ──

def test_profit_factor_basic():
    # wins 0.3+0.2=0.5 ; losses 0.4 -> 1.25
    assert profit_factor([0.3, 0.2, -0.4]) == 1.25


def test_profit_factor_no_losses_sentinel():
    assert profit_factor([0.3, 0.2]) == 999.0


def test_profit_factor_no_wins():
    assert profit_factor([-0.3, -0.2]) == 0.0


def test_profit_factor_empty():
    assert profit_factor([]) == 0.0
