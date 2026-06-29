"""Cross-venue arbitrage detector (maker/taker aware).

Given an aligned subject S priced on both venues, a locked position exists when
you can hold YES_S on one venue and NO_S on the other for a combined cost (plus
fees) below $1 — one contract must pay $1 at resolution.

Two execution models, very different economics:
  TAKER — cross the spread, pay the ASK on both legs, pay taker fees.
  MAKER — post resting limit orders, (optimistically) fill at the BID on both
          legs, pay ~0 fees (Polymarket maker = 0; Kalshi maker = 25% of taker).
          This is market-making: the edge is real only if BOTH orders actually
          fill before the underlying moves (fill + adverse-selection risk).

All prices are dollars in [0, 1] from each venue's live top-of-book.
"""
from __future__ import annotations

from services.calculator import kalshi_fee, polymarket_fee


def _evaluate(*, yes_cost_k, no_cost_k, yes_cost_p, no_cost_p, maker):
    """Return (best_edge, direction) over the two arb legs.

    Leg A: YES on Kalshi + NO on Polymarket.
    Leg B: YES on Polymarket + NO on Kalshi.
    `*_cost_*` are the per-contract dollar costs to acquire that outcome.
    """
    # Leg A: YES@kalshi + NO@poly
    cost_a = yes_cost_k + no_cost_p
    fees_a = kalshi_fee(yes_cost_k, maker) + polymarket_fee(no_cost_p, maker)
    edge_a = 1.0 - cost_a - fees_a

    # Leg B: YES@poly + NO@kalshi
    cost_b = yes_cost_p + no_cost_k
    fees_b = polymarket_fee(yes_cost_p, maker) + kalshi_fee(no_cost_k, maker)
    edge_b = 1.0 - cost_b - fees_b

    if edge_a >= edge_b:
        return edge_a, "YES@kalshi + NO@poly"
    return edge_b, "YES@poly + NO@kalshi"


def detect_arb(
    *,
    kalshi_yes_bid: float,
    kalshi_yes_ask: float,
    poly_subject_bid: float,
    poly_subject_ask: float,
    poly_other_bid: float,
    poly_other_ask: float,
    mode: str = "taker",
    threshold: float = 0.0,
) -> dict:
    """Best cross-venue arb edge for one aligned subject under `mode`.

    TAKER: buy at the ask on each leg (NO@kalshi costs 1 - yes_bid).
    MAKER: post and fill at the bid on each leg (NO@kalshi costs 1 - yes_ask),
           fees ~0. Optimistic — assumes both resting orders fill.

    Returns {has_arb, best_edge, direction, mode}. `has_arb` is best_edge > threshold.
    """
    maker = mode == "maker"
    if maker:
        yes_cost_k = kalshi_yes_bid
        no_cost_k = 1.0 - kalshi_yes_ask
        yes_cost_p = poly_subject_bid
        no_cost_p = poly_other_bid
    else:
        yes_cost_k = kalshi_yes_ask
        no_cost_k = 1.0 - kalshi_yes_bid
        yes_cost_p = poly_subject_ask
        no_cost_p = poly_other_ask

    best_edge, direction = _evaluate(
        yes_cost_k=yes_cost_k, no_cost_k=no_cost_k,
        yes_cost_p=yes_cost_p, no_cost_p=no_cost_p, maker=maker,
    )
    return {
        "has_arb": best_edge > threshold,
        "best_edge": round(best_edge, 4),
        "direction": direction,
        "mode": mode,
    }
