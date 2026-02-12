"""Performance and calibration endpoints.

Provides aggregate accuracy stats (Brier score, hit rate, P&L) and
calibration curve data for evaluating the AI forecaster over time.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Query

from models.schemas import (
    CalibrationResponse,
    CategoryPerformanceResponse,
    CostSummaryResponse,
    PerformanceAggregateResponse,
    PnLTimeSeriesResponse,
)
from models.database import (
    get_performance_aggregate,
    get_calibration_data,
    get_cost_summary,
    get_pnl_timeseries,
    get_performance_by_category,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/performance", tags=["performance"])


@router.get("", response_model=PerformanceAggregateResponse)
async def get_performance(
    from_date: Optional[str] = Query(None, description="ISO date filter (>=)"),
    to_date: Optional[str] = Query(None, description="ISO date filter (<=)"),
) -> PerformanceAggregateResponse:
    """Get aggregate performance statistics.

    Returns total resolved markets, hit rate, average Brier score,
    cumulative P&L, and average edge. Optionally filtered by date range.
    """
    data = get_performance_aggregate(from_date=from_date, to_date=to_date)
    return PerformanceAggregateResponse(**data)


@router.get("/calibration", response_model=CalibrationResponse)
async def get_calibration(
    from_date: Optional[str] = Query(None, description="ISO date filter (>=)"),
    to_date: Optional[str] = Query(None, description="ISO date filter (<=)"),
) -> CalibrationResponse:
    """Get calibration curve data.

    Returns 10 buckets (0-10%, 10-20%, ..., 90-100%) with the
    average predicted probability, actual resolution frequency,
    and count of forecasts in each bucket.
    """
    buckets = get_calibration_data(from_date=from_date, to_date=to_date)
    return CalibrationResponse(buckets=buckets)


@router.get("/pnl-history", response_model=PnLTimeSeriesResponse)
async def get_pnl_history(
    from_date: Optional[str] = Query(None, description="ISO date filter (>=)"),
    to_date: Optional[str] = Query(None, description="ISO date filter (<=)"),
) -> PnLTimeSeriesResponse:
    """Get P&L time series with cumulative sum.

    Each data point represents a resolved market with its individual P&L
    and the running cumulative total. Ordered chronologically.
    """
    data = get_pnl_timeseries(from_date=from_date, to_date=to_date)
    return PnLTimeSeriesResponse(data_points=data)


@router.get("/by-category", response_model=CategoryPerformanceResponse)
async def get_perf_by_category() -> CategoryPerformanceResponse:
    """Get performance statistics grouped by market category/sport."""
    data = get_performance_by_category()
    return CategoryPerformanceResponse(categories=data)


@router.get("/costs", response_model=CostSummaryResponse)
async def get_costs() -> CostSummaryResponse:
    """Get API cost summary (today, this week, this month, all time)."""
    data = get_cost_summary()
    return CostSummaryResponse(**data)
