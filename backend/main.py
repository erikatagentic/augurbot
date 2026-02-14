"""AugurBot — FastAPI backend.

Entry point for the backend server.  Configures structured logging,
sets up the APScheduler for periodic scans, includes all API routers,
and exposes health and configuration endpoints.

Start with:
    uvicorn main:app --host 0.0.0.0 --port 8000
"""

import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from anthropic import AsyncAnthropic
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from models.schemas import (
    ConfigResponse,
    ConfigUpdateRequest,
    HealthResponse,
)
from models.database import (
    get_config,
    get_supabase,
    update_config,
)
from routers import markets, recommendations, performance, scan, trades
from services.scan_progress import get_last_scan_summary
from services.scheduler import configure_scheduler, scheduler, get_next_scan_time

# ── Structured logging ──────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ── Application lifespan ────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup and shutdown of background services.

    On startup:
      1. Verify the Supabase database connection.
      2. Configure and start the APScheduler.

    On shutdown:
      1. Gracefully shut down the scheduler.
    """
    # -- Startup --
    logger.info("Starting AugurBot backend")

    # Verify database connection
    try:
        db = get_supabase()
        db.table("markets").select("id").limit(1).execute()
        logger.info("Database connection verified")
    except Exception:
        logger.exception(
            "Database connection failed — the app will start but scans will fail"
        )

    # Verify Anthropic API key
    if settings.anthropic_api_key:
        try:
            client = AsyncAnthropic(api_key=settings.anthropic_api_key)
            await client.messages.count_tokens(
                model=settings.default_model,
                messages=[{"role": "user", "content": "test"}],
            )
            logger.info("Anthropic API key verified")
        except Exception:
            logger.exception(
                "Anthropic API key verification failed — scans will fail"
            )
    else:
        logger.warning(
            "ANTHROPIC_API_KEY not set — AI estimation will not work"
        )

    # Configure and start scheduler
    try:
        configure_scheduler()
        scheduler.start()
        logger.info("Scheduler started")
    except Exception:
        logger.exception("Scheduler failed to start")

    yield

    # -- Shutdown --
    logger.info("Shutting down AugurBot backend")
    try:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
    except Exception:
        logger.exception("Error shutting down scheduler")


# ── FastAPI app ─────────────────────────────────────────────────────

app = FastAPI(
    title="AugurBot",
    description="AI-powered prediction market edge detection",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://localhost:\d+$",
    allow_origins=[
        "https://augurbot.com",
        "https://www.augurbot.com",
        "https://augurbot-eonbjliar-heyagentic.vercel.app",
        "https://augurbot-heyagentic.vercel.app",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ─────────────────────────────────────────────────────────

app.include_router(scan.router)
app.include_router(markets.router)
app.include_router(recommendations.router)
app.include_router(performance.router)
app.include_router(trades.router)


# ── Root-level endpoints ────────────────────────────────────────────


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Backend health check.

    Returns:
      - Database connection status.
      - Timestamp of the most recent market snapshot (proxy for last scan time).
      - Platform availability flags.
    """
    db_connected = False
    last_scan_at = None

    # Prefer in-memory scan summary (updates even when 0 markets found)
    summary = get_last_scan_summary()
    if summary.get("completed_at"):
        try:
            last_scan_at = datetime.fromisoformat(summary["completed_at"])
        except (ValueError, TypeError):
            pass

    try:
        db = get_supabase()
        # Fall back to latest snapshot if no in-memory summary
        if last_scan_at is None:
            result = (
                db.table("market_snapshots")
                .select("captured_at")
                .order("captured_at", desc=True)
                .limit(1)
                .execute()
            )
            if result.data:
                last_scan_at = datetime.fromisoformat(
                    result.data[0]["captured_at"]
                )
        else:
            # Still verify DB is reachable
            db.table("config").select("key").limit(1).execute()
        db_connected = True
    except Exception:
        logger.exception("Health check: database query failed")

    platforms = {
        "kalshi": bool(
            (settings.kalshi_api_key and (settings.kalshi_private_key_path or settings.kalshi_private_key))
            or (settings.kalshi_email and settings.kalshi_password)
        ),
    }

    next_scan = get_next_scan_time()

    return HealthResponse(
        status="ok" if db_connected else "degraded",
        last_scan_at=last_scan_at,
        next_scan_at=next_scan,
        database_connected=db_connected,
        platforms=platforms,
    )


@app.get("/config", response_model=ConfigResponse)
async def get_configuration() -> ConfigResponse:
    """Get current configuration values.

    Merges defaults from ``settings`` with any overrides stored in the
    database ``config`` table.
    """
    config_data = get_config()
    return ConfigResponse(**config_data)


@app.put("/config", response_model=ConfigResponse)
async def update_configuration(request: ConfigUpdateRequest) -> ConfigResponse:
    """Update configuration values.

    Only non-``None`` fields in the request body are applied. Changes
    are persisted to the database ``config`` table and will survive
    server restarts.

    Returns:
        The full updated configuration.
    """
    updates = request.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(
            status_code=400,
            detail="No configuration values provided to update.",
        )

    update_config(updates)
    logger.info("Configuration updated: %s", list(updates.keys()))

    # Reconfigure scheduler if scan times changed
    if "scan_times" in updates:
        from services.scheduler import reconfigure_scan_schedule

        reconfigure_scan_schedule(updates["scan_times"])

    return ConfigResponse(**get_config())


@app.post("/notifications/test")
async def test_notification():
    """Send a test notification to verify email/Slack configuration."""
    from services.notifier import send_test_notification

    results = await send_test_notification()
    if not results:
        raise HTTPException(
            status_code=400,
            detail="No notification channels configured. Set an email address or Slack webhook in Settings.",
        )
    return {"status": "sent", "channels": results}
