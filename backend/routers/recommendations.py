"""Recommendation endpoints.

Provides access to active bet recommendations (sorted by EV) and
historical recommendations with their outcomes.
"""

import logging

from fastapi import APIRouter, Query

from models.schemas import RecommendationListResponse, MarketRow
from models.database import (
    get_active_recommendations,
    get_recommendation_history,
    get_market,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


def _build_markets_dict(recommendations: list) -> dict[str, MarketRow]:
    """Look up the market for each recommendation and return a dict keyed by market_id.

    Args:
        recommendations: List of RecommendationRow objects.

    Returns:
        Dict mapping market_id to MarketRow.
    """
    markets: dict[str, MarketRow] = {}
    for rec in recommendations:
        if rec.market_id not in markets:
            market = get_market(rec.market_id)
            if market is not None:
                markets[rec.market_id] = market
    return markets


@router.get("", response_model=RecommendationListResponse)
async def list_active_recommendations() -> RecommendationListResponse:
    """Get all active recommendations, sorted by EV (highest first).

    Each recommendation includes the associated market metadata
    in the ``markets`` dict (keyed by market_id).
    """
    recommendations = get_active_recommendations()
    markets = _build_markets_dict(recommendations)

    return RecommendationListResponse(
        recommendations=recommendations,
        markets=markets,
    )


@router.get("/history", response_model=RecommendationListResponse)
async def list_recommendation_history(
    limit: int = Query(50, ge=1, le=500, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> RecommendationListResponse:
    """Get historical recommendations (all statuses), most recent first.

    Each recommendation includes the associated market metadata
    in the ``markets`` dict (keyed by market_id).
    """
    recommendations = get_recommendation_history(limit=limit, offset=offset)
    markets = _build_markets_dict(recommendations)

    return RecommendationListResponse(
        recommendations=recommendations,
        markets=markets,
    )
