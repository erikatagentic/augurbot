"""Performance analytics — failure classification + risk metrics.

Guide Step 5 ("compound"): every loss should make the next trade better.
These are pure functions so results.py can compute them and unit tests can
pin the logic. Max-drawdown reuses services.risk_guard.max_drawdown_pct.
"""
from __future__ import annotations

import math

# Failure taxonomy (auto-detectable from resolved-market data).
FAIL_BAD_ESTIMATE = "bad_estimate"      # our model was wrong, market was closer
FAIL_NEWS_TIMING = "news_timing"        # line moved hard against us after entry
FAIL_EXTERNAL_SHOCK = "external_shock"  # market itself was very wrong (surprise)


def classify_failure(
    ai_estimate: float,
    market_price: float,
    outcome: bool,
    correct: bool,
    clv: float | None = None,
) -> str | None:
    """Classify why a resolved bet lost. Returns None if it was correct.

    Signals (outcome mapped to 1.0/0.0):
      - external_shock: the MARKET also priced the wrong side strongly
        (err_mkt > 0.55) — nobody saw it coming.
      - news_timing: closing-line value moved hard against us (clv <= -0.08)
        — information arrived after we entered.
      - bad_estimate: default — our estimate missed (and usually missed by
        more than the market did).

    'execution' failures (bad fill / slippage) need fill-vs-intended data not
    present on resolved markets, so they are not auto-classified here.
    """
    if correct:
        return None

    actual = 1.0 if outcome else 0.0
    err_mkt = abs(market_price - actual)

    if err_mkt > 0.55:
        return FAIL_EXTERNAL_SHOCK
    if clv is not None and clv <= -0.08:
        return FAIL_NEWS_TIMING
    return FAIL_BAD_ESTIMATE


def sharpe(returns: list[float]) -> float:
    """Per-bet Sharpe ratio = mean(returns) / stdev(returns).

    NOT annualized — bets aren't uniformly spaced, so this is a unitless
    risk-adjusted return across the bet series. 0.0 if <2 points or zero
    variance.
    """
    clean = [float(r) for r in returns if r is not None]
    if len(clean) < 2:
        return 0.0
    mean = sum(clean) / len(clean)
    var = sum((x - mean) ** 2 for x in clean) / (len(clean) - 1)
    sd = math.sqrt(var)
    if sd < 1e-9:        # treat float noise as zero variance
        return 0.0
    return round(mean / sd, 4)


def profit_factor(pnls: list[float]) -> float:
    """Gross profit / gross loss. >1.5 is healthy. Returns 999.0 as a sentinel
    for 'wins, no losses' (infinity isn't JSON-serializable); 0.0 if no wins.
    """
    clean = [float(p) for p in pnls if p is not None]
    gross_win = sum(p for p in clean if p > 0)
    gross_loss = abs(sum(p for p in clean if p < 0))
    if gross_loss == 0:
        return 999.0 if gross_win > 0 else 0.0
    return round(gross_win / gross_loss, 2)
