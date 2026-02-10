"""Performance and calibration endpoints.

Provides aggregate accuracy stats (Brier score, hit rate, P&L) and
calibration curve data for evaluating the AI forecaster over time.
"""

import logging

from fastapi import APIRouter

from models.schemas import (
    CalibrationResponse,
    PerformanceAggregateResponse,
)
from models.database import (
    get_performance_aggregate,
    get_calibration_data,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/performance", tags=["performance"])


@router.get("", response_model=PerformanceAggregateResponse)
async def get_performance() -> PerformanceAggregateResponse:
    """Get aggregate performance statistics.

    Returns total resolved markets, hit rate, average Brier score,
    cumulative P&L, and average edge.
    """
    data = get_performance_aggregate()
    return PerformanceAggregateResponse(**data)


@router.get("/calibration", response_model=CalibrationResponse)
async def get_calibration() -> CalibrationResponse:
    """Get calibration curve data.

    Returns 10 buckets (0-10%, 10-20%, ..., 90-100%) with the
    average predicted probability, actual resolution frequency,
    and count of forecasts in each bucket.
    """
    buckets = get_calibration_data()
    return CalibrationResponse(buckets=buckets)
