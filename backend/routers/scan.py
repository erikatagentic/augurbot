"""Scan trigger endpoints.

Allows the frontend (or manual curl) to kick off a market scan
as a background task so the HTTP response returns immediately.
"""

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException

from models.schemas import Platform, ScanStatusResponse
from services.scanner import execute_scan

logger = logging.getLogger(__name__)

router = APIRouter(tags=["scan"])


@router.post("/scan", response_model=ScanStatusResponse)
async def trigger_full_scan(
    background_tasks: BackgroundTasks,
) -> ScanStatusResponse:
    """Trigger a full scan across all enabled platforms.

    The scan runs as a background task. The response returns
    immediately with ``status="running"``.
    """
    logger.info("Scan endpoint: full scan triggered")
    background_tasks.add_task(execute_scan)

    return ScanStatusResponse(status="running")


@router.post("/scan/{platform}", response_model=ScanStatusResponse)
async def trigger_platform_scan(
    platform: str,
    background_tasks: BackgroundTasks,
) -> ScanStatusResponse:
    """Trigger a scan for a single platform.

    Args:
        platform: Platform name (``polymarket``, ``kalshi``, or ``manifold``).

    Returns:
        ScanStatusResponse with ``status="running"`` and the platform name.

    Raises:
        HTTPException 400: If the platform is not supported.
    """
    valid_platforms = {p.value for p in Platform if p != Platform.metaculus}
    if platform not in valid_platforms:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported platform: {platform}. "
            f"Valid options: {', '.join(sorted(valid_platforms))}",
        )

    logger.info("Scan endpoint: %s scan triggered", platform)
    background_tasks.add_task(execute_scan, platform=platform)

    return ScanStatusResponse(status="running", platform=platform)
