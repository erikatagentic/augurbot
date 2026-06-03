"""Deterministic bet-decision pipeline shared by the backtester and live scan.

Single source of truth for: executable-price EV, the recommendation gate, the
spread gate, Kelly sizing, and per-contract simulated P&L.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from services.calculator import (  # noqa: E402
    calculate_ev,
    calculate_kelly,
    should_recommend,
)
from models.schemas import Confidence  # noqa: E402


def spread_too_wide(yes_ask: float, yes_bid: float, max_spread: float) -> bool:
    """True if the book is too wide/stale to trade."""
    if yes_ask <= 0 or yes_bid <= 0:
        return True
    return (yes_ask - yes_bid) > max_spread


def evaluate_market(
    ai_estimate: float,
    yes_ask: float,
    yes_bid: float,
    confidence: str,
    kelly_fraction: float = 0.20,
    max_bet_fraction: float = 0.03,
    max_spread: float = 0.10,
    platform: str = "kalshi",
) -> dict:
    """Run the full decision for one market against the executable book.

    Returns a dict with ``recommend`` (bool) and, when recommended,
    ``direction``, ``edge``, ``ev``, ``kelly_fraction``.
    """
    mid = (yes_ask + yes_bid) / 2.0
    base = {"recommend": False, "direction": None, "edge": 0.0, "ev": 0.0,
            "kelly_fraction": 0.0}

    if spread_too_wide(yes_ask, yes_bid, max_spread):
        return base

    ev_data = calculate_ev(ai_estimate, mid, platform,
                           yes_ask=yes_ask, yes_bid=yes_bid)
    if ev_data is None:
        return base

    # Divergence/coin-flip gate uses the executable entry price for the side.
    entry = yes_ask if ev_data["direction"] == "yes" else yes_bid
    if not should_recommend(ev_data["ev"], confidence, ai_estimate, entry):
        return base

    kelly = calculate_kelly(
        ev_data["edge"], entry, ev_data["direction"],
        Confidence(confidence), kelly_fraction, max_bet_fraction,
    )
    return {
        "recommend": kelly > 0,
        "direction": ev_data["direction"],
        "edge": ev_data["edge"],
        "ev": ev_data["ev"],
        "kelly_fraction": kelly,
    }


def simulate_pnl_per_contract(direction: str, entry_price: float,
                              outcome: bool) -> float:
    """Profit/loss for one contract entered at ``entry_price`` (YES-equivalent).

    YES: pay entry_price, receive 1.0 if outcome True.
    NO: pay (1 - entry_price), receive 1.0 if outcome False.
    """
    if direction == "yes":
        return round((1.0 - entry_price) if outcome else -entry_price, 4)
    no_cost = 1.0 - entry_price
    return round((1.0 - no_cost) if not outcome else -no_cost, 4)
