"""EV calculation, Kelly sizing, and performance metrics.

Pure math — no external API calls, no database access.  Every function
is deterministic given its inputs.
"""

from models.schemas import Confidence, Direction, Platform
from config import settings

# ── Constants ────────────────────────────────────────────────────────

CONFIDENCE_MULTIPLIERS: dict[Confidence, float] = {
    Confidence.high: 1.0,
    Confidence.medium: 0.6,
    Confidence.low: 0.3,
}

PLATFORM_FEES: dict[str, float] = {
    Platform.polymarket.value: settings.polymarket_fee,
    Platform.kalshi.value: settings.kalshi_fee,
    Platform.manifold.value: settings.manifold_fee,
}


# ── Fee lookup ───────────────────────────────────────────────────────


def get_platform_fee(platform: str) -> float:
    """Return the trading fee for a given platform.

    Args:
        platform: Platform identifier (e.g. ``"polymarket"``).

    Returns:
        Fee as a decimal (e.g. 0.02 for 2%).  Defaults to 0.02
        if the platform is not recognised.
    """
    return PLATFORM_FEES.get(platform, 0.02)


# ── Expected Value ───────────────────────────────────────────────────


def calculate_ev(
    ai_probability: float,
    market_price: float,
    platform: str,
) -> dict | None:
    """Compare the AI estimate to the market price and return EV data.

    Evaluates both YES and NO directions and returns whichever has
    positive expected value.  If neither direction is profitable after
    fees, returns ``None``.

    Args:
        ai_probability: AI's estimated probability (0.01 – 0.99).
        market_price: Current market price for YES (0 – 1).
        platform: Platform name for fee lookup.

    Returns:
        Dict with ``direction``, ``edge``, and ``ev`` for the better
        direction, or ``None`` if no edge exists.
    """
    fee = get_platform_fee(platform)

    # YES direction
    yes_edge = ai_probability - market_price
    yes_ev = yes_edge - fee

    # NO direction
    no_edge = market_price - ai_probability
    no_ev = no_edge - fee

    if yes_ev > 0 and yes_ev >= no_ev:
        return {
            "direction": Direction.yes.value,
            "edge": round(yes_edge, 4),
            "ev": round(yes_ev, 4),
        }

    if no_ev > 0:
        return {
            "direction": Direction.no.value,
            "edge": round(no_edge, 4),
            "ev": round(no_ev, 4),
        }

    return None


# ── Kelly Criterion ──────────────────────────────────────────────────


def calculate_kelly(
    edge: float,
    market_price: float,
    direction: str,
    confidence: Confidence,
    kelly_fraction: float | None = None,
    max_bet_fraction: float | None = None,
) -> float:
    """Compute the recommended bet size as a fraction of bankroll.

    Uses fractional Kelly with a confidence-based multiplier to reduce
    variance.

    Args:
        edge: Absolute edge (AI prob minus market price, or vice versa).
        market_price: Current YES price (0 – 1).
        direction: ``"yes"`` or ``"no"``.
        confidence: AI confidence level for the estimate.
        kelly_fraction: Override for the base fractional Kelly
                        (default from settings).
        max_bet_fraction: Maximum allowed fraction of bankroll for a
                          single bet (default from settings).

    Returns:
        Recommended fraction of bankroll to wager (>= 0).
    """
    if kelly_fraction is None:
        kelly_fraction = settings.kelly_fraction
    if max_bet_fraction is None:
        max_bet_fraction = settings.max_single_bet_fraction

    # Full Kelly formula — guard against division by zero
    if direction == Direction.yes.value:
        denominator = 1.0 - market_price
        if denominator <= 0:
            return 0.0
        full_kelly = edge / denominator
    else:
        if market_price <= 0:
            return 0.0
        full_kelly = edge / market_price

    # Apply fractional Kelly and confidence multiplier
    confidence_mult = CONFIDENCE_MULTIPLIERS.get(confidence, 0.6)
    adjusted = full_kelly * kelly_fraction * confidence_mult

    # Floor at 0, cap at max single-bet fraction
    return round(max(0.0, min(adjusted, max_bet_fraction)), 4)


# ── Brier Score ──────────────────────────────────────────────────────


def calculate_brier_score(probability: float, outcome: bool) -> float:
    """Compute the Brier score for a single forecast.

    Lower is better (0 = perfect, 1 = worst possible).

    Args:
        probability: Forecasted probability of YES (0 – 1).
        outcome: ``True`` if the event resolved YES, ``False`` for NO.

    Returns:
        Brier score (probability - outcome_val) ** 2.
    """
    outcome_val = 1.0 if outcome else 0.0
    return round((probability - outcome_val) ** 2, 4)


# ── Profit & Loss ────────────────────────────────────────────────────


def calculate_pnl(
    market_price: float,
    direction: str,
    outcome: bool,
    kelly_fraction_used: float,
    bankroll: float,
) -> float:
    """Calculate profit or loss for a resolved binary-option bet.

    Assumes standard binary payout: win pays ``1 - price`` on the
    amount wagered (YES) or ``price`` (NO); loss forfeits the wager.

    Args:
        market_price: Price at which the position was entered (YES side).
        direction: ``"yes"`` or ``"no"``.
        outcome: ``True`` if the market resolved YES.
        kelly_fraction_used: Fraction of bankroll wagered.
        bankroll: Total bankroll at time of bet.

    Returns:
        Profit (positive) or loss (negative) in currency units.
    """
    wager = kelly_fraction_used * bankroll

    if direction == Direction.yes.value:
        if outcome:
            # Win: paid market_price per share, receive 1.0 per share
            pnl = wager * (1.0 - market_price) / market_price
        else:
            # Lose: forfeit wager
            pnl = -wager
    else:
        # NO direction
        if not outcome:
            # Win: paid (1 - market_price) per share, receive 1.0 per share
            no_price = 1.0 - market_price
            if no_price <= 0:
                return 0.0
            pnl = wager * market_price / no_price
        else:
            # Lose: forfeit wager
            pnl = -wager

    return round(pnl, 4)


# ── Recommendation gate ─────────────────────────────────────────────


def should_recommend(
    ev: float,
    min_edge: float | None = None,
) -> bool:
    """Decide whether the expected value is high enough to recommend.

    Args:
        ev: Expected value after fees.
        min_edge: Override for the minimum edge threshold
                  (default from settings).

    Returns:
        ``True`` if the EV meets or exceeds the threshold.
    """
    if min_edge is None:
        min_edge = settings.min_edge_threshold
    return ev >= min_edge
