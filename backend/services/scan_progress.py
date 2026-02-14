"""In-memory scan progress tracker (single-user, single-process)."""

from datetime import datetime, timezone
from typing import Optional

_progress: dict = {
    "is_running": False,
    "phase": "idle",
    "platform": None,
    "started_at": None,
    "completed_at": None,
    "markets_found": 0,
    "markets_total": 0,
    "markets_processed": 0,
    "markets_researched": 0,
    "markets_skipped": 0,
    "recommendations_created": 0,
    "current_market": None,
    "error": None,
}


def start_scan(platform: Optional[str] = None) -> None:
    """Reset progress and mark scan as running."""
    _progress.update(
        {
            "is_running": True,
            "phase": "fetching",
            "platform": platform,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "markets_found": 0,
            "markets_total": 0,
            "markets_processed": 0,
            "markets_researched": 0,
            "markets_skipped": 0,
            "recommendations_created": 0,
            "current_market": None,
            "error": None,
        }
    )


def set_markets_found(total_from_api: int, total_after_filter: int) -> None:
    """Called after fetching + date filtering."""
    _progress["markets_found"] = total_from_api
    _progress["markets_total"] = total_after_filter
    _progress["phase"] = "researching"


def market_processing(question: str) -> None:
    """Called when starting to process a specific market."""
    _progress["current_market"] = question[:80]


def market_done(result: Optional[str]) -> None:
    """Called when a market finishes processing."""
    _progress["markets_processed"] += 1
    _progress["current_market"] = None
    if result == "skipped":
        _progress["markets_skipped"] += 1
    elif result == "researched":
        _progress["markets_researched"] += 1
    elif result == "recommended":
        _progress["markets_researched"] += 1
        _progress["recommendations_created"] += 1


def update_batch_status(total: int, completed: int) -> None:
    """Update progress during batch processing."""
    _progress["phase"] = "researching"
    _progress["current_market"] = f"Batch processing... ({completed}/{total} done)"
    _progress["markets_processed"] = completed


def complete_scan() -> None:
    """Mark scan as complete."""
    _progress["is_running"] = False
    _progress["phase"] = "complete"
    _progress["completed_at"] = datetime.now(timezone.utc).isoformat()
    _progress["current_market"] = None


def fail_scan(error_msg: str) -> None:
    """Mark scan as failed."""
    _progress["is_running"] = False
    _progress["phase"] = "failed"
    _progress["completed_at"] = datetime.now(timezone.utc).isoformat()
    _progress["error"] = error_msg
    _progress["current_market"] = None


def reset_stale_scan(max_age_minutes: int = 120) -> bool:
    """Reset scan progress if stuck in 'running' state too long.

    Called on startup to clear state from a crashed process.
    Returns True if a stale scan was reset.
    """
    if not _progress["is_running"]:
        return False

    started_str = _progress.get("started_at")
    if not started_str:
        _progress["is_running"] = False
        _progress["phase"] = "idle"
        return True

    from datetime import timedelta

    try:
        started = datetime.fromisoformat(started_str)
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - started > timedelta(minutes=max_age_minutes):
            _progress["is_running"] = False
            _progress["phase"] = "failed"
            _progress["error"] = "Scan timed out after restart"
            _progress["completed_at"] = datetime.now(timezone.utc).isoformat()
            _progress["current_market"] = None
            return True
    except (ValueError, TypeError):
        _progress["is_running"] = False
        _progress["phase"] = "idle"
        return True

    return False


def get_progress() -> dict:
    """Return a copy of current progress state."""
    return dict(_progress)


# ── Last scan summary (persists in memory until next restart) ──

_last_scan_summary: dict = {}


def save_scan_summary(summary: dict) -> None:
    """Save summary of the most recent completed scan."""
    _last_scan_summary.clear()
    _last_scan_summary.update(summary)


def get_last_scan_summary() -> dict:
    """Return the last scan summary (empty dict if no scan has completed)."""
    return dict(_last_scan_summary)
