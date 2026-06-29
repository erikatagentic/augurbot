"""Cross-venue arbitrage detector.

Given an aligned subject S priced on both venues, a locked arb exists when you
can buy YES_S on one venue and NO_S on the other for a combined cost (plus
fees) below $1 — one of the two contracts must pay $1 at resolution.

Binary mechanics:
  Kalshi  YES_S costs  yes_ask_S ;  NO_S costs (1 - yes_bid_S)
  Poly    YES_S costs  price[subject_index] ;  NO_S costs price[other_index]
          (the two-player market's other outcome IS NO_S)

All prices are dollars in [0, 1]. Polymarket prices here are Gamma midpoints —
good enough to FLAG an opportunity in paper mode; live execution must re-price
against the CLOB order book (the same slippage discipline as the risk guard).
"""
from __future__ import annotations

from services.calculator import get_platform_fee


def _kfee(price: float) -> float:
    return get_platform_fee("kalshi", price)


def _pfee(price: float) -> float:
    return get_platform_fee("polymarket", price)


def detect_arb(
    *,
    kalshi_yes_ask: float,
    kalshi_yes_bid: float,
    poly_subject_price: float,
    poly_other_price: float,
    threshold: float = 0.0,
) -> dict:
    """Compute the best cross-venue arb edge for one aligned subject.

    Returns a dict with `has_arb`, `best_edge` (net of fees, in dollars per
    $1 contract pair), `direction`, and per-leg detail. `has_arb` is True when
    best_edge > threshold.
    """
    # Leg A: buy YES_S on Kalshi, NO_S on Polymarket.
    cost_a = kalshi_yes_ask + poly_other_price
    fees_a = _kfee(kalshi_yes_ask) + _pfee(poly_other_price)
    edge_a = 1.0 - cost_a - fees_a

    # Leg B: buy YES_S on Polymarket, NO_S on Kalshi.
    kalshi_no_cost = 1.0 - kalshi_yes_bid
    cost_b = poly_subject_price + kalshi_no_cost
    fees_b = _pfee(poly_subject_price) + _kfee(kalshi_no_cost)
    edge_b = 1.0 - cost_b - fees_b

    if edge_a >= edge_b:
        best_edge, direction = edge_a, "YES@kalshi + NO@poly"
        legs = {
            "buy_yes_on": "kalshi", "yes_cost": round(kalshi_yes_ask, 4),
            "buy_no_on": "polymarket", "no_cost": round(poly_other_price, 4),
            "total_cost": round(cost_a, 4), "fees": round(fees_a, 4),
        }
    else:
        best_edge, direction = edge_b, "YES@poly + NO@kalshi"
        legs = {
            "buy_yes_on": "polymarket", "yes_cost": round(poly_subject_price, 4),
            "buy_no_on": "kalshi", "no_cost": round(kalshi_no_cost, 4),
            "total_cost": round(cost_b, 4), "fees": round(fees_b, 4),
        }

    return {
        "has_arb": best_edge > threshold,
        "best_edge": round(best_edge, 4),
        "direction": direction,
        "legs": legs,
        "edge_a": round(edge_a, 4),
        "edge_b": round(edge_b, 4),
    }
